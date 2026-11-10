#!/usr/bin/env python3
"""Build the WAISS website (waiss.teloscircle.com) into dist/: landing page, editions, slides, privacy page.

    python3 -X utf8 tools/deck.py && node tools/export-deck.js   # the deck + its PNGs (npm run deck)
    python3 -X utf8 tools/site.py                                 # -> dist/   (npm run site)

Inputs
  editions/*.json   one per meetup. Website fields:
                    deck   folder name of a built deck: build/<deck>/index.html + meta.json and exports/<deck>/*.png
                    parts  [{"title", "from"}]: a part starts at the slide named `from` (name without the NN- prefix)
                           and runs until the next part
                    talks  [{"title", "speaker", "url" | "pdf"}]: slides people bring themselves (PDF in the repo or a link)
                    shown in the part whose title contains "Show"
Upcoming vs. past is decided in the browser (Vienna time): an edition counts as past from the day after it.
The build does the same for visitors without JavaScript, and CI rebuilds every night.
"""
import html, json, re, shutil, sys, unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deck as D  # noqa: E402
import render as R  # noqa: E402

ROOT = R.ROOT
OUT = ROOT / "dist"
DOMAIN = "waiss.teloscircle.com"
SITE = f"https://{DOMAIN}"
REPO = "https://github.com/topsrek/waiss"
VIENNA = ZoneInfo("Europe/Vienna")
HOURS = 3  # calendar entry length; the open round has no fixed end
TELOS = {
    "website": "https://www.teloscircle.com", "events": "https://events.teloscircle.com",
    "links": "https://links.teloscircle.com", "imprint": "https://events.teloscircle.com/imprint",
    "linkedin": "https://www.linkedin.com/company/telos-circle", "instagram": "https://www.instagram.com/teloscircle",
    "x": "https://x.com/CircleTelos",
}
esc = html.escape
FONT_LINK = '<link rel="stylesheet" href="{p}fonts/fonts.css">'


# ------------------------------------------------------------------------------------- data
def load_editions():
    eds = []
    for f in sorted((ROOT / "editions").glob("*.json")):
        ed = json.loads(f.read_text(encoding="utf-8"))
        num = int(re.sub(r"\D", "", ed["edition"]))
        start = datetime.strptime(f'{ed["datum"]} {ed["zeit"]}', "%d.%m.%Y %H:%M").replace(tzinfo=VIENNA)
        ed.update(num=num, slug=str(num), start=start, day=start.date().isoformat(),
                  luma=ed.get("anmeldung"), slides=load_slides(ed))
        eds.append(ed)
    return sorted(eds, key=lambda e: e["start"])


def load_slides(ed):
    """[(part title, [(index 1.., name), ...]), ...] from build/<deck>/meta.json and the edition's parts."""
    if not ed.get("deck"):
        return []
    meta = ROOT / "build" / ed["deck"] / "meta.json"
    if not meta.exists():
        sys.exit(f"{meta} missing: run `npm run deck` first")
    names = json.loads(meta.read_text(encoding="utf-8"))["slides"]
    parts = ed.get("parts") or [{"title": "Slides", "from": names[0].split("-", 1)[1]}]
    starts = {}
    for p in parts:
        hit = [i for i, n in enumerate(names) if n.split("-", 1)[1] == p["from"]]
        if not hit:
            sys.exit(f'{ed["edition"]}: part "{p["title"]}" starts at unknown slide "{p["from"]}"')
        starts[hit[0]] = p["title"]
    starts.setdefault(0, parts[0]["title"])
    out, cur = [], None
    for i, n in enumerate(names):
        if i in starts:
            cur = (starts[i], [])
            out.append(cur)
        cur[1].append((i + 1, n))
    return out


# ------------------------------------------------------------------------------------- pieces
def wordmark(text, cls="wm", label=None):
    """Secession lettering as ONE scalable SVG (render.txt draws fixed-size pixels)."""
    raw = text.upper().replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE").replace("ß", "SS")
    raw = "".join(c for c in unicodedata.normalize("NFD", raw) if unicodedata.category(c) != "Mn")
    x, parts = 0.0, []
    for ch in raw:
        vx, w, d = R.G.get(ch, R.G[" "])
        if d:
            parts.append(f'<path transform="translate({x - vx:.2f} 0)" d="{d}"/>')
        x += w + 20
    width = x - 20
    return (f'<svg class="{cls}" viewBox="-8 -8 {width + 16:.1f} 116" role="img" aria-label="{esc(label or text)}">'
            f'<g fill="none" stroke="currentColor" stroke-width="16" stroke-linejoin="miter">{"".join(parts)}</g></svg>')


def svg_file(name, cls="", fill=None):
    raw = (ROOT / "assets" / "logo" / f"{name}.svg").read_text(encoding="utf-8")
    raw = re.sub(r"<title>.*?</title>", "", raw)
    if fill:
        raw = raw.replace("<path ", f'<path fill="{fill}" ', 1)
    return raw.replace("<svg ", f'<svg class="{cls}" aria-hidden="true" ', 1)


ARROW = '<span aria-hidden="true">&nbsp;&#8599;</span>'


def ext(href, label, cls=""):
    return f'<a class="{cls}" href="{esc(href)}" target="_blank" rel="noopener">{label}{ARROW}</a>'


def when(ed, year=True):
    s = ed["start"]
    return f'{s:%a} {s.day} {s:%b}{" " + str(s.year) if year else ""} · {s:%H:%M}'


def place(ed):
    return f'{esc(ed["ort_lang"])} · {esc(ed["adresse"])}'


def ics(ed):
    fmt = lambda t: t.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Telos Circle//WAISS//EN", "BEGIN:VEVENT",
             f"UID:waiss-{ed['num']}@{DOMAIN}", f"DTSTAMP:{fmt(datetime.now(timezone.utc))}",
             f"DTSTART:{fmt(ed['start'])}", f"DTEND:{fmt(ed['start'] + timedelta(hours=HOURS))}",
             f"SUMMARY:WAISS {ed['edition']} – Wiener AI Software Stammtisch",
             f"LOCATION:{ed['ort_lang']}\\, {ed['adresse'].replace(',', chr(92) + ',')}",
             f"URL:{ed['luma'] or SITE}", f"DESCRIPTION:AI recap\\, show & tell and an open round. {ed['luma'] or SITE}",
             "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


# ------------------------------------------------------------------------------------- sections
def hero(eds, today):
    cards = []
    for ed in eds:
        live = ed["day"] >= today
        is_next = live and ed is next(e for e in eds if e["day"] >= today)
        cards.append(
            f'<div class="next" data-next="{ed["day"]}"{"" if is_next else " hidden"}>'
            f'<div class="eyebrow"><span data-when>{"Tonight" if ed["day"] == today else "Next"}</span> · WAISS {esc(ed["edition"])}</div>'
            f'<div class="next-date">{when(ed, year=False)}</div>'
            f'<div class="next-place">{place(ed)}</div>'
            f'<div class="btns">' + (ext(ed["luma"], "Register on Luma", "btn") if ed["luma"] else "")
            + f'<a class="btn ghost" href="{ed["slug"]}/waiss-{ed["slug"]}.ics" download>Add to calendar</a></div></div>')
    none_next = not any(e["day"] >= today for e in eds)
    cards.append(f'<div class="next" data-next="tba"{"" if none_next else " hidden"}>'
                 '<div class="eyebrow">Next edition</div><div class="next-date">Date coming soon</div>'
                 '<div class="next-place">We meet about once a month in Vienna. The Discord hears first.</div>'
                 f'<div class="btns">{ext(eds[-1]["links"]["discord"], "Join the Discord", "btn")}</div></div>')
    return f'''
<section class="hero" id="top" data-cam="0.82,0.7,-0.04,0" data-cam-m="0.38,0.14,0.3,0">
  <div class="wrap">
    <h1>{wordmark("WAISS", "wm big")}</h1>
    <p class="acro"><b>W</b>iener <b>AI</b> <b>S</b>oftware <b>S</b>tammtisch</p>
    <p class="lead">A cozy get-together (Stammtisch) for Viennese AI builders.</p>
    {"".join(cards)}
  </div>
</section>'''


def format_(eds, today):
    rows = [("01", "AI Recap", "What mattered in AI last month", "20 min"),
            ("02", "Show &amp; Tell", "Tool tips and your own projects", "short talks"),
            ("03", "Open round", "Chat, discuss, meet people", "open end")]
    r = "".join(f'<li><span class="n">{n}</span><span class="t">{t}</span><span class="w">{w}</span><span class="m">{m}</span></li>'
                for n, t, w, m in rows)
    nxt = next((e for e in eds if e["day"] >= today and e["luma"]), None)
    cta = (f'<div class="btns" data-until="{nxt["day"]}">{ext(nxt["luma"], "Register on Luma", "btn")}</div>' if nxt else "")
    return f'''
<section id="format" data-cam="0.6,-0.95,0.15,80" data-cam-m="0.3,-0.2,0.42,80">
  <div class="wrap">
    <div class="eyebrow">Every edition</div>
    <ul class="agenda">{r}</ul>
    {cta}
  </div>
</section>'''


def ed_row(ed, today):
    past = ed["day"] < today
    links = []
    if ed["luma"]:
        links.append(ext(ed["luma"], f'<span data-upcoming{" hidden" if past else ""}>Register</span>'
                                     f'<span data-past{"" if past else " hidden"}>Luma</span>', "lnk"))
    if ed["slides"] or ed.get("talks"):
        links.append(f'<a class="lnk" href="#slides-{ed["slug"]}">Slides&nbsp;&#8595;</a>')
    badge = f'<span class="badge" data-today{"" if ed["day"] == today else " hidden"}>Today</span>'
    return (f'<li class="ed-row" data-day="{ed["day"]}"><span class="n">{esc(ed["edition"])}</span>'
            f'<span class="d">{when(ed)} {badge}</span><span class="p">{place(ed)}</span>'
            f'<span class="l">{"".join(links)}</span></li>')


def editions(eds, today):
    up = [e for e in eds if e["day"] >= today]
    past = [e for e in eds if e["day"] < today][::-1]
    return f'''
<section id="editions" data-cam="0.5,0.95,-0.32,140" data-cam-m="0.3,0.2,-0.4,140">
  <div class="wrap">
    <div class="eyebrow">Editions</div>
    <h2>Upcoming</h2>
    <ul class="rows" id="up">{"".join(ed_row(e, today) for e in up)}</ul>
    <p class="empty" id="up-empty"{" hidden" if up else ""}>The next date is coming soon.
      {ext(eds[-1]["links"]["discord"], "Discord", "lnk")}</p>
    <h2 class="h-past">Past</h2>
    <ul class="rows" id="past">{"".join(ed_row(e, today) for e in past)}</ul>
    <p class="empty" id="past-empty"{" hidden" if past else ""}>Nothing yet. Come to the first one.</p>
  </div>
</section>'''


def slides_panel(ed, first):
    s = ed["slug"]
    parts = [(t, list(sl)) for t, sl in ed["slides"]]
    talks = ed.get("talks") or []
    if talks and not any("show" in t.lower() for t, _ in parts):
        parts.append(("Show & Tell", []))
    blocks = []
    for k, (title, sl) in enumerate(parts, 1):
        thumbs = "".join(
            f'<li><a href="{s}/#{i}" target="_blank" rel="noopener" aria-label="{esc(title)}, slide {i}">'
            f'<img src="{s}/slides/{n}.webp" width="480" height="270" loading="lazy" decoding="async" alt="">'
            f'<span class="sn">{i:02d}</span></a></li>' for i, n in sl)
        if "show" in title.lower():
            for t in talks:
                href = t.get("url") or f'{s}/talks/{Path(t["pdf"]).name}'
                thumbs += (f'<li class="talk"><a href="{esc(href)}" target="_blank" rel="noopener">'
                           f'<span class="eyebrow">Talk</span><strong>{esc(t["title"])}</strong>'
                           f'<span>{esc(t.get("speaker", ""))}</span><span class="sn">{"PDF" if t.get("pdf") else "Link"}&#8599;</span></a></li>')
        count = len(sl) + (len(talks) if "show" in title.lower() else 0)
        start = f'<a class="lnk" href="{s}/#{sl[0][0]}" target="_blank" rel="noopener">Present from here{ARROW}</a>' if sl else ""
        blocks.append(f'<div class="part"><div class="part-head"><span class="n">{k:02d}</span><h3>{esc(title)}</h3>'
                      f'<span class="c">{count} {"slide" if count == 1 else "slides"}</span>{start}</div>'
                      f'<ul class="thumbs">{thumbs}</ul></div>')
    actions = (ext(f"{s}/", "Present", "btn") if ed["slides"] else "") + (
        f'<a class="btn ghost" href="{s}/waiss-{s}-slides.pdf" download>PDF</a>' if ed.get("pdf") else "")
    return (f'<div class="panel" id="slides-{s}" role="tabpanel" aria-label="WAISS {esc(ed["edition"])}"'
            f'{"" if first else " data-off"}><div class="panel-head"><div><div class="eyebrow">WAISS {esc(ed["edition"])}</div>'
            f'<div class="panel-date">{when(ed)}</div></div><div class="btns">{actions}</div></div>{"".join(blocks)}</div>')


def slides(eds):
    have = [e for e in eds if e["slides"] or e.get("talks")][::-1]
    if not have:
        return ""
    tabs = "".join(f'<button role="tab" data-tab="slides-{e["slug"]}" aria-selected="{"true" if k == 0 else "false"}">'
                   f'{esc(e["edition"])}</button>' for k, e in enumerate(have))
    return f'''
<section id="slides" data-cam="0.32,0.74,0.3,250" data-cam-m="0.26,0.2,0.42,250">
  <div class="wrap">
    <h2>Slides</h2>
    <p class="sub">Click a slide to present from there.</p>
    <div class="tabs" role="tablist" aria-label="Edition">{tabs}</div>
    {"".join(slides_panel(e, k == 0) for k, e in enumerate(have))}
  </div>
</section>'''


def contribute(eds):
    L = eds[-1]["links"]
    return f'''
<section id="contribute" data-cam="0.75,-0.98,-0.1,60" data-cam-m="0.3,-0.2,-0.42,60">
  <div class="wrap">
    <div class="eyebrow">Open source</div>
    <h2>Bring your slides</h2>
    <div class="gh">
      <div>
        <p class="sub">Slides, blob and this page are open source. Giving a talk? Add your slides by pull request.</p>
        <ol class="steps">
          <li><span class="n">01</span><span>Fork <code>topsrek/waiss</code>.</span></li>
          <li><span class="n">02</span><span>Add a layout in <code>tools/deck.py</code>, or a PDF under <code>talks</code>.</span></li>
          <li><span class="n">03</span><span>Open a pull request. Merged means deployed.</span></li>
        </ol>
        <div class="btns">{ext(REPO, svg_file("github", "ico", "currentColor") + "topsrek/waiss", "btn")}
          {ext(L["discord"], "Talk to us on Discord", "btn ghost")}</div>
      </div>
      <pre class="code" aria-label="Example"><span class="cm"># editions/002.json</span>
"talks": [{{
  "title": "Agents that file my taxes",
  "speaker": "Your Name · @handle",
  "pdf": "talks/002/agents-taxes.pdf"
}}]</pre>
    </div>
  </div>
</section>'''


def footer(eds, prefix=""):
    L = eds[-1]["links"]
    col = lambda title, items: (f'<div class="fcol"><div class="eyebrow">{title}</div><ul>'
                                + "".join(f"<li>{i}</li>" for i in items) + "</ul></div>")
    year = datetime.now(VIENNA).year
    return f'''
<footer data-cam="0.7,0.0,-0.62,300" data-cam-m="0.34,0.0,-0.5,300">
  <div class="wrap">
    <div class="fgrid">
      <div class="fbrand">
        <a href="{TELOS["website"]}" target="_blank" rel="noopener" aria-label="Telos Circle">{svg_file("telos-circle-wortmarke", "tc")}</a>
        <p>WAISS is a format by Telos Circle, a Vienna-based nonprofit fostering interdisciplinary innovation
          across science, technology and entrepreneurship.</p>
      </div>
      {col("WAISS", [f'<a href="{prefix}#editions">Editions</a>', f'<a href="{prefix}#slides">Slides</a>',
                     ext(REPO, "GitHub"), ext(L["discord"], "Discord")])}
      {col("Telos Circle", [ext(TELOS["website"], "Website"), ext(TELOS["events"], "Events"),
                            ext(TELOS["links"], "All links")])}
      {col("Follow", [ext(TELOS["linkedin"], "LinkedIn"), ext(TELOS["instagram"], "Instagram"), ext(TELOS["x"], "X")])}
    </div>
    <div class="fbase">
      <span>© {year} Telos Circle</span>
      <span><a href="{TELOS["imprint"]}" target="_blank" rel="noopener">Imprint</a>
        <a href="{prefix}privacy/">Privacy</a></span>
    </div>
  </div>
</footer>'''


def privacy(eds):
    return f'''
<section class="legal" data-cam="0.7,0.95,0.1,200" data-cam-m="0.4,0.12,0.4,200">
  <div class="wrap narrow">
    <div class="eyebrow"><a href="../">← WAISS</a></div>
    <h2>Privacy</h2>
    <p>This website is a static page. It sets no cookies, has no analytics or tracking, keeps no access logs and loads
      nothing from third parties: fonts and images come from this domain, and the blob is drawn by your own browser.</p>
    <h3>Who is responsible</h3>
    <p>Telos Circle, Vienna. Contact details and legal information are in the
      <a href="{TELOS["imprint"]}" target="_blank" rel="noopener">imprint</a>.</p>
    <h3>Hosting</h3>
    <p>The site runs on a server of Telos Circle at Hetzner Online GmbH in Germany. To deliver a page, the server
      processes your IP address for the duration of the request (Art. 6(1)(f) GDPR). It is not stored.</p>
    <h3>Links to other services</h3>
    <p>Registration runs on Luma, the community on Discord and the source code on GitHub. Those services only receive
      data once you follow a link there, under their own privacy policies.</p>
    <h3>Your rights</h3>
    <p>You have the right to access, rectification, erasure, restriction, objection and data portability. You can also
      complain to the Austrian Data Protection Authority (<a href="https://www.dsb.gv.at" target="_blank" rel="noopener">dsb.gv.at</a>).</p>
  </div>
</section>'''


# ------------------------------------------------------------------------------------- page
def page(title, desc, body, eds, prefix="", canonical=SITE + "/"):
    css = (ROOT / "tools" / "site.css").read_text(encoding="utf-8")
    js = (ROOT / "tools" / "site.js").read_text(encoding="utf-8")
    blob = json.dumps({"fs": D.FS, "presets": R.PRESETS, "variant": D.VARIANT})
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{SITE}/og.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#F5F3EE">
<link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml">
{FONT_LINK.format(p=prefix)}
<style>{css}</style>
</head>
<body>
<canvas id="blob" aria-hidden="true"></canvas>
<header class="top"><div class="wrap">
  <div class="brand"><a class="home" href="{prefix or "#top"}" aria-label="WAISS">{wordmark("WAISS", "wm small")}</a>
    <a class="by" href="{TELOS["links"]}" target="_blank" rel="noopener" aria-label="Telos Circle">{svg_file("telos-circle-by", "tcby")}</a></div>
  <nav aria-label="Sections"><a href="{prefix}#editions">Editions</a><a href="{prefix}#slides">Slides</a>
    <a href="{prefix}#contribute">GitHub</a></nav>
</div></header>
<main>{body}</main>
{footer(eds, prefix)}
<script id="blob-data" type="application/json">{blob}</script>
<script>{js}</script>
</body>
</html>
'''


def favicon():
    vx, w, d = R.G["W"]
    s = 100 + 2 * 26
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}"><rect width="{s}" height="{s}" rx="34" fill="#F5F3EE"/>'
            f'<g transform="translate({(s - w * .62) / 2:.1f} {(s - 62) / 2:.1f}) scale(.62)"><path transform="translate({-vx} 0)" '
            f'd="{d}" fill="none" stroke="#1F1E1B" stroke-width="16"/></g></svg>')


def main():
    eds = load_editions()
    today = datetime.now(VIENNA).date().isoformat()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "assets" / "fonts", OUT / "fonts")
    (OUT / "favicon.svg").write_text(favicon(), encoding="utf-8")
    shutil.copy(ROOT / "exports" / "001" / "luma-cover.png", OUT / "og.png")
    for f in ("Dockerfile", "nginx.conf"):  # dist/ deploys as it is: Coolify builds this Dockerfile
        shutil.copy(ROOT / "deploy" / f, OUT / f)

    for ed in eds:
        d = OUT / ed["slug"]
        d.mkdir()
        (d / f'waiss-{ed["slug"]}.ics').write_text(ics(ed), encoding="utf-8", newline="")
        if ed["slides"]:
            deck_html = (ROOT / "build" / ed["deck"] / "index.html").read_text(encoding="utf-8")
            assert D.FONTS in deck_html, "deck does not use tools/deck.py's FONTS"
            (d / "index.html").write_text(deck_html.replace(D.FONTS, FONT_LINK.format(p="../")), encoding="utf-8")
            png = ROOT / "exports" / ed["deck"]
            (d / "slides").mkdir()
            for _, sl in ed["slides"]:
                for _, n in sl:
                    src = png / f"{n}.png"
                    if not src.exists():
                        sys.exit(f"{src} missing: run `npm run deck` again (the PNGs are older than the deck)")
                    with Image.open(src) as im:
                        im.convert("RGB").resize((960, 540), Image.LANCZOS).save(d / "slides" / f"{n}.webp", quality=82, method=6)
            pdf = png / "waiss-slides.pdf"
            ed["pdf"] = pdf.exists()
            if ed["pdf"]:
                shutil.copy(pdf, d / f'waiss-{ed["slug"]}-slides.pdf')
        for t in ed.get("talks") or []:
            if t.get("pdf"):
                (d / "talks").mkdir(exist_ok=True)
                shutil.copy(ROOT / t["pdf"], d / "talks" / Path(t["pdf"]).name)

    desc = "WAISS – Wiener AI Software Stammtisch: a monthly get-together in Vienna for everyone who builds with AI. By Telos Circle."
    body = hero(eds, today) + format_(eds, today) + editions(eds, today) + slides(eds) + contribute(eds)
    (OUT / "index.html").write_text(page("WAISS – Wiener AI Software Stammtisch", desc, body, eds), encoding="utf-8")
    (OUT / "privacy").mkdir()
    (OUT / "privacy" / "index.html").write_text(
        page("Privacy – WAISS", "Privacy policy of waiss.teloscircle.com", privacy(eds), eds, "../", SITE + "/privacy/"),
        encoding="utf-8")
    (OUT / "404.html").write_text(
        page("Not found – WAISS", desc, '<section class="legal" data-cam="1.0,0.6,0,0" data-cam-m="0.6,0,0.3,0"><div class="wrap narrow">'
             '<div class="eyebrow">404</div><h2>Nothing here.</h2><p><a class="btn" href="/">Back to WAISS</a></p></div></section>',
             eds, "/"), encoding="utf-8")
    n = sum(1 for _ in OUT.rglob("*") if _.is_file())
    print(f"built {OUT} ({n} files, today {today} in Vienna)")


if __name__ == "__main__":
    main()
