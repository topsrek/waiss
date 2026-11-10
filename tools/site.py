#!/usr/bin/env python3
"""Build the WAISS website (waiss.teloscircle.com) into dist/: landing page, editions, slides, privacy page.

    python3 -X utf8 tools/deck.py && node tools/export-deck.js   # the deck + its PNGs (npm run deck)
    python3 -X utf8 tools/site.py                                 # -> dist/   (npm run site)

Inputs
  editions/*.json   one per meetup. Website fields:
                    deck   folder name of a built deck: build/<deck>/index.html + meta.json and exports/<deck>/*.png
                    parts  [{"title", "from"}]: a part starts at the slide named `from` (name without the NN- prefix)
                           and runs until the next part
                    talks  [{"title", "speaker", "html" | "file" | "url"}]: slides people bring themselves (an HTML folder,
                           a PDF/PPT in the repo, or a link)
                    shown in the part whose title contains "Show"
Upcoming vs. past is decided in the browser (Vienna time): an edition counts as past from the day after it.
The build does the same for visitors without JavaScript, and CI rebuilds every night.
"""
import html, json, os, re, shutil, subprocess, sys, unicodedata
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
TELOS = {
    "website": "https://www.teloscircle.com", "events": "https://events.teloscircle.com",
    "links": "https://links.teloscircle.com", "imprint": "https://events.teloscircle.com/imprint",
    "linkedin": "https://www.linkedin.com/company/telos-circle", "instagram": "https://www.instagram.com/teloscircle",
    "x": "https://x.com/CircleTelos",
}
NAME = "WAISS – Wiener AI Software Stammtisch"
# one sentence that answers who/what/where/how often; reused by meta description, JSON-LD and llms.txt
ABOUT = ("WAISS (Wiener AI Software Stammtisch) is a free meetup in Vienna for everyone who builds with AI, "
         "about once a month, organized by the nonprofit Telos Circle.")
DESC = ("Free monthly meetup in Vienna for people who build with AI: AI recap of the month, show & tell, open round. "
        "The KI-Stammtisch in Wien by Telos Circle.")
FORMAT = [("AI Recap", "What mattered in AI last month", "20 min"),
          ("Show &amp; Tell", "Tool tips and your own projects", "short talks"),
          ("Open round", "Chat, discuss, meet people", "open end")]
esc = html.escape
FONT_LINK = '<link rel="stylesheet" href="{p}fonts/fonts.css">'


# ------------------------------------------------------------------------------------- data
def load_editions():
    eds = []
    for f in sorted((ROOT / "editions").glob("*.json")):
        ed = json.loads(f.read_text(encoding="utf-8"))
        num = int(re.sub(r"\D", "", ed["edition"]))
        start = datetime.strptime(f'{ed["datum"]} {ed["zeit"]}', "%d.%m.%Y %H:%M").replace(tzinfo=VIENNA)
        ed.update(num=num, slug=str(num), start=start, file=f.relative_to(ROOT).as_posix(), day=start.date().isoformat(),
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
def wordmark(text, cls="wm", label=None, hi=()):
    """Secession lettering as ONE scalable SVG (render.txt draws fixed-size pixels). Letters at the indices in `hi`
    get class="hi" (drawn in ink while the rest takes the colour of the text)."""
    raw = text.upper().replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE").replace("ß", "SS")
    raw = "".join(c for c in unicodedata.normalize("NFD", raw) if unicodedata.category(c) != "Mn")
    x, parts = 0.0, []
    for ch in raw:
        vx, w, d = R.G.get(ch, R.G[" "])
        if d:
            parts.append(f'<path{" class='hi'" if len(parts) in hi else ""} transform="translate({x - vx:.2f} 0)" d="{d}"/>')
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


# ------------------------------------------------------------------------------------- sections
def hero():
    return f'''
<section class="hero" id="top" data-cam="0.82,0.7,-0.04,0" data-cam-m="0.38,0.14,0.3,0">
  <div class="wrap">
    <h1>{wordmark("WAISS", "wm big")}</h1>
    <p class="acro">{wordmark("Wiener AI", "l1", "Wiener AI Software Stammtisch", hi=(0, 6, 7))}
      {wordmark("Software Stammtisch", "l2", "", hi=(0, 8))}</p>
    <p class="lead">A cozy get-together (Stammtisch) for Viennese AI builders.</p>
  </div>
</section>'''


def format_(eds, today):
    r = "".join(f'<li><span class="n">{n:02d}</span><span class="t">{t}</span><span class="w">{w}</span><span class="m">{m}</span></li>'
                for n, (t, w, m) in enumerate(FORMAT, 1))
    nxt = next((e for e in eds if e["day"] >= today and e["luma"]), None)
    cta = (f'<div class="btns" data-until="{nxt["day"]}">{ext(nxt["luma"], "Register on Luma", "btn")}</div>' if nxt else "")
    return f'''
<section id="format" data-cam="0.6,0.92,0.12,80" data-cam-m="0.3,0.2,0.4,80">
  <div class="wrap">
    <div class="eyebrow">Every edition</div>
    <ul class="agenda">{r}</ul>
    <p class="sub">Free to attend, about once a month in Vienna, for everyone who builds with AI.</p>
    {cta}
  </div>
</section>'''


def state(day, today):
    return "past" if day < today else "today" if day == today else "upcoming"


def has_slides(ed):
    return bool(ed["slides"] or ed.get("talks"))


def ed_row(ed, today, pre=""):
    st = state(ed["day"], today)
    s = ed["start"]
    links = []
    if ed["luma"]:
        links.append(ext(ed["luma"], f'<span data-upcoming{" hidden" if st == "past" else ""}>Register</span>'
                                     f'<span data-past{"" if st == "past" else " hidden"}>Luma</span>', "lnk"))
    if has_slides(ed):
        links.append(f'<a class="lnk" href="{pre}editions/{ed["slug"]}/">Slides&nbsp;&#8594;</a>')
    return (f'<li class="ed" data-day="{ed["day"]}" data-state="{st}">'
            f'{wordmark(ed["edition"], "num", "WAISS " + ed["edition"])}'
            f'<div class="ed-when"><div class="ed-date">{s:%a} {s.day} {s:%b %Y} · {s:%H:%M}</div>'
            f'<div class="ed-place">{esc(ed["ort_lang"])}, {esc(ed["adresse"])}</div></div>'
            f'<span class="st" data-st>{st.capitalize()}</span>'
            f'<div class="ed-links">{"".join(links)}</div></li>')


def editions(eds, today):
    nxt = int(re.sub(r"\D", "", eds[-1]["edition"])) + 1
    tba = (f'<li class="ed tba" data-tba{"" if all(e["day"] <= today for e in eds) else " hidden"}>'
           f'{wordmark(f"#{nxt}", "num", f"WAISS #{nxt}")}'
           f'<div class="ed-when"><div class="ed-date">Date coming soon</div>'
           f'<div class="ed-place">About once a month in Vienna.</div></div>'
           f'<span class="st">Next</span><div class="ed-links">{ext(eds[-1]["links"]["discord"], "Discord", "lnk")}</div></li>')
    # upcoming first (soonest on top), then "Past" and the past ones (most recent on top); site.js redoes this live
    past = [e for e in eds if e["day"] < today][::-1]
    up = [e for e in eds if e["day"] >= today]
    sep = f'<li class="ed-sep" data-sep{"" if past else " hidden"}>Past</li>'
    rows = "".join(ed_row(e, today) for e in up) + "{tba}" + sep + "".join(ed_row(e, today) for e in past)
    return f'''
<section id="editions" data-cam="0.5,0.95,-0.32,140" data-cam-m="0.3,0.2,-0.4,140">
  <div class="wrap">
    <h2>Editions</h2>
    <ol class="eds" id="eds">{rows.replace("{tba}", tba)}</ol>
  </div>
</section>'''


def talk_src(t):
    return t.get("html") or t.get("file") or t.get("pdf")  # "pdf" = older name of "file"


def talk_href(slug, t):
    if t.get("url"):
        return t["url"]
    return f'{slug}/talks/{Path(talk_src(t)).name}' + ("/" if t.get("html") else "")


def talk_kind(t):
    return "Slides" if t.get("html") else Path(talk_src(t)).suffix[1:].upper() if talk_src(t) else "Link"


def slides_panel(ed, pre="", head=True):
    s = pre + ed["slug"]
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
                href = talk_href(s, t)
                thumbs += (f'<li class="talk"><a href="{esc(href)}" target="_blank" rel="noopener">'
                           f'<span class="eyebrow">Talk</span><strong>{esc(t["title"])}</strong>'
                           f'<span>{esc(t.get("speaker", ""))}</span><span class="sn">{talk_kind(t)}&#8599;</span></a></li>')
        count = len(sl) + (len(talks) if "show" in title.lower() else 0)
        start = f'<a class="lnk" href="{s}/#{sl[0][0]}" target="_blank" rel="noopener">Present from here{ARROW}</a>' if sl else ""
        blocks.append(f'<div class="part"><div class="part-head"><span class="n">{k:02d}</span><h3>{esc(title)}</h3>'
                      f'<span class="c">{count} {"slide" if count == 1 else "slides"}</span>{start}</div>'
                      f'<ul class="thumbs">{thumbs}</ul></div>')
    actions = (ext(f"{s}/", "Present", "btn") if ed["slides"] else "") + (
        f'<a class="btn ghost" href="{s}/waiss-{s}-slides.pdf" download>PDF</a>' if ed.get("pdf") else "")
    return (f'<div class="panel" id="slides-{ed["slug"]}"><div class="panel-head">'
            + (f'<div><div class="eyebrow">WAISS {esc(ed["edition"])}</div><div class="panel-date">{when(ed)}</div></div>' if head else "")
            + f'<div class="btns">{actions}</div></div>{"".join(blocks)}</div>')


def slides(eds):
    """The current slides: the latest edition that has any. Older ones live on /editions/<n>/."""
    cur = next((e for e in eds[::-1] if has_slides(e)), None)
    if not cur:
        return ""
    older = [e for e in eds if has_slides(e) and e is not cur]
    more = (f'<p class="sub">Earlier editions: ' + ", ".join(
        f'<a class="lnk" href="editions/{e["slug"]}/">{esc(e["edition"])}</a>' for e in older[::-1]) + "</p>") if older else ""
    return f'''
<section id="slides" data-cam="0.32,0.74,0.3,250" data-cam-m="0.26,0.2,0.42,250">
  <div class="wrap">
    <h2>Current slides</h2>
    <p class="sub">Click a slide to present from there.</p>
    {slides_panel(cur)}
    {more}
  </div>
</section>'''


def edition_page(ed):
    """/editions/<n>/: one edition with all its slides."""
    s = ed["start"]
    luma = ext(ed["luma"], "Luma", "btn ghost") if ed["luma"] else ""
    return f'''
<section class="edition" data-cam="0.5,0.95,-0.32,140" data-cam-m="0.3,0.2,-0.4,140">
  <div class="wrap">
    <div class="eyebrow"><a href="../../#editions">&#8592; All editions</a></div>
    <h1 class="ed-h">{wordmark(ed["edition"], "num big-num", "WAISS " + ed["edition"])}</h1>
    <div class="ed-date">{s:%A} {s.day} {s:%B %Y} · {s:%H:%M}</div>
    <div class="ed-place">{esc(ed["ort_lang"])}, {esc(ed["adresse"])}</div>
    {slides_panel(ed, "../../", head=False).replace('<div class="btns">', '<div class="btns">' + luma, 1)}
  </div>
</section>'''


MAIL = ("events", "teloscircle.com")  # put together in the browser, against scrapers


def contribute(eds):
    env = ('<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" '
           'aria-hidden="true"><rect x="2.5" y="5" width="19" height="14" rx="2.5"/><path d="M3 6.5l9 6.5 9-6.5"/></svg>')
    master = (f'<a class="btn ghost" href="master/" target="_blank" rel="noopener">All slide layouts{ARROW}</a>'
              if (ROOT / "build" / "master" / "index.html").exists() else "")
    return f'''
<section id="contribute" data-cam="0.62,0.9,-0.08,60" data-cam-m="0.3,0.2,-0.42,60">
  <div class="wrap">
    <h2>Want to present something next time?</h2>
    <ul class="ways">
      <li>{svg_file("github", "ico", "currentColor")}<span>Open a pull request on {ext(REPO, "github.com/topsrek/waiss", "lnk")}</span></li>
      <li>{env}<span>or email <a class="lnk" data-mail="{MAIL[0]}|{MAIL[1]}" href="#contribute">{MAIL[0]} [at] {MAIL[1]}</a></span></li>
    </ul>
    <p class="formats">HTML preferred · PPT and PDF work too</p>
    <div class="btns">{master}</div>
  </div>
</section>'''


def footer(eds, prefix=""):
    L = eds[-1]["links"]
    col = lambda title, items: (f'<div class="fcol"><div class="eyebrow">{title}</div><ul>'
                                + "".join(f"<li>{i}</li>" for i in items) + "</ul></div>")
    year = datetime.now(VIENNA).year
    return f'''
<footer data-cam="0.5,0.95,-0.38,300" data-cam-m="0.3,0.2,-0.45,300">
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


# ------------------------------------------------------------------------------------- search engines and LLMs
# Everything a crawler reads besides the visible page: <head> tags, JSON-LD, robots.txt, sitemap.xml, llms.txt and a
# text version of every deck (slides.md). All of it comes from editions/*.json and the built decks.
ORG_ID, SERIES_ID, SITE_ID = SITE + "/#telos-circle", SITE + "/#waiss", SITE + "/#website"
OG_W, OG_H = 1200, 630
ICONS = []  # filled by build_icons(): extra <link>s for the PNG/ICO icons once assets/logo/waiss-blob*.png exists


def head(title, desc, canonical, prefix="", image=None, robots=None, ld=None, alt=None):
    """<head> tags for search engines and link previews (shared by the site pages and the decks)."""
    image = image or f"{SITE}/og.jpg"
    tags = [f"<title>{esc(title)}</title>", f'<meta name="description" content="{esc(desc)}">']
    if robots:
        tags.append(f'<meta name="robots" content="{robots}">')
    else:
        tags.append(f'<link rel="canonical" href="{canonical}">')
    tags += [f'<meta property="og:site_name" content="WAISS">', '<meta property="og:type" content="website">',
             '<meta property="og:locale" content="en_GB">',
             f'<meta property="og:title" content="{esc(title)}">', f'<meta property="og:description" content="{esc(desc)}">',
             f'<meta property="og:url" content="{canonical}">', f'<meta property="og:image" content="{image}">',
             f'<meta property="og:image:width" content="{OG_W}">', f'<meta property="og:image:height" content="{OG_H}">',
             f'<meta property="og:image:alt" content="{esc(NAME)}">', '<meta name="twitter:card" content="summary_large_image">',
             '<meta name="theme-color" content="#F5F3EE">',
             f'<link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml">',
             *[i.format(p=prefix) for i in ICONS]]
    if alt:
        tags.append(f'<link rel="alternate" type="text/markdown" href="{alt}" title="Slides as text">')
    if ld:
        js = json.dumps(ld, ensure_ascii=False, indent=1).replace("</", "<\\/")
        tags.append(f'<script type="application/ld+json">{js}</script>')
    return "\n".join(tags)


def address(ed):
    """'Mariahilfer Str. 73, 1060 Wien' -> schema.org PostalAddress."""
    street, _, rest = ed["adresse"].partition(", ")
    m = re.match(r"(\d{4})\s+(.+)", rest)
    return {"@type": "PostalAddress", "streetAddress": street, "postalCode": m[1] if m else None,
            "addressLocality": m[2] if m else rest, "addressRegion": "Wien", "addressCountry": "AT"}


def organization():
    return {"@type": "Organization", "@id": ORG_ID, "name": "Telos Circle", "url": TELOS["website"],
            "logo": f"{SITE}/telos-circle.svg",
            "description": "Vienna-based nonprofit fostering interdisciplinary innovation across science, technology "
                           "and entrepreneurship.",
            "address": {"@type": "PostalAddress", "addressLocality": "Wien", "addressCountry": "AT"},
            "sameAs": [TELOS["website"], TELOS["linkedin"], TELOS["instagram"], TELOS["x"], TELOS["events"]]}


def event_ld(ed):
    s = ed["slug"]
    ev = {"@type": "Event", "@id": f"{SITE}/{s}/#event", "name": f"WAISS {ed['edition']} – Wiener AI Software Stammtisch",
          "description": f"WAISS {ed['edition']}: an AI recap of the month, show & tell and an open round, at "
                         f"{ed['ort_lang']} in Vienna. Free, organized by Telos Circle.",
          "startDate": ed["start"].isoformat(timespec="minutes"),
          "eventStatus": "https://schema.org/" + ed.get("status", "EventScheduled"),
          "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
          "location": {"@type": "Place", "name": ed["ort_lang"], "address": address(ed)},
          "image": ed["images"],
          "organizer": {"@type": "Organization", "@id": ORG_ID, "name": "Telos Circle", "url": TELOS["website"]},
          "isAccessibleForFree": True, "url": f"{SITE}/", "superEvent": {"@id": SERIES_ID}}
    if ed["luma"]:
        ev["offers"] = {"@type": "Offer", "url": ed["luma"], "price": 0, "priceCurrency": "EUR",
                        "availability": "https://schema.org/InStock"}
    if ed["slides"]:
        ev["subjectOf"] = {"@type": "PresentationDigitalDocument", "name": f"WAISS {ed['edition']} slides",
                           "url": f"{SITE}/{s}/", "encodingFormat": "text/html"}
    return ev


def site_ld(eds):
    series = {"@type": "EventSeries", "@id": SERIES_ID, "name": NAME,
              "alternateName": ["WAISS", "Wiener AI Software Stammtisch", "KI-Stammtisch Wien"], "description": ABOUT,
              "url": f"{SITE}/", "image": f"{SITE}/og.jpg", "organizer": {"@id": ORG_ID},
              "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode", "isAccessibleForFree": True,
              "location": {"@type": "Place", "name": "Vienna",
                           "address": {"@type": "PostalAddress", "addressLocality": "Wien", "addressCountry": "AT"}},
              "keywords": "AI meetup Vienna, KI Stammtisch Wien, AI Software, Show and Tell",
              "subEvent": [{"@id": f"{SITE}/{e['slug']}/#event"} for e in eds]}
    website = {"@type": "WebSite", "@id": SITE_ID, "url": f"{SITE}/", "name": "WAISS",
               "alternateName": "Wiener AI Software Stammtisch", "inLanguage": "en", "publisher": {"@id": ORG_ID}}
    return {"@context": "https://schema.org", "@graph": [website, organization(), series, *map(event_ld, eds)]}


def deck_ld(ed):
    return {"@context": "https://schema.org", "@type": "PresentationDigitalDocument", "@id": f"{SITE}/{ed['slug']}/",
            "name": f"WAISS {ed['edition']} slides", "url": f"{SITE}/{ed['slug']}/", "inLanguage": "en",
            "datePublished": ed["day"], "author": {"@type": "Organization", "name": "Telos Circle", "url": TELOS["website"]},
            "about": {"@type": "Event", "@id": f"{SITE}/{ed['slug']}/#event", "name": f"WAISS {ed['edition']}",
                      "startDate": ed["start"].isoformat(timespec="minutes"),
                      "location": {"@type": "Place", "name": ed["ort_lang"], "address": address(ed)}},
            "isPartOf": {"@id": SITE_ID}, "image": f"{SITE}/{ed['slug']}/og.jpg"}


def deck_page(raw, ed=None, master=False):
    """A built deck as the site serves it: fonts from the site, plus the <head> tags (title, description, canonical,
    JSON-LD). Only <head> and <html lang> change; the slides stay as tools/deck.py built them."""
    assert D.FONTS in raw, "deck does not use tools/deck.py's FONTS"
    raw = raw.replace(D.FONTS, FONT_LINK.format(p="../"))
    if master:
        tags = head("WAISS – Master slides", "Every slide layout of the WAISS decks, with placeholder content.",
                    f"{SITE}/master/", "../", robots="noindex, follow")
    else:
        s = ed["start"]
        parts = [p for p, _ in ed["slides"]]
        tags = head(f"WAISS {ed['edition']} slides – AI recap {s:%B %Y}, Vienna",
                    f"Slides of WAISS {ed['edition']}, the Wiener AI Software Stammtisch on {s:%a} {s.day} {s:%b %Y} at "
                    f"{ed['ort_lang']}, Vienna: {', '.join(parts)}.",
                    f"{SITE}/{ed['slug']}/", "../", image=f"{SITE}/{ed['slug']}/og.jpg", ld=deck_ld(ed), alt="slides.md")
    raw, n = re.subn(r"<title>.*?</title>", lambda m: tags, raw, count=1, flags=re.S)
    assert n == 1, "deck has no <title>"
    return re.sub(r'<html lang="[^"]*">', '<html lang="en">', raw, count=1)


BLOCK = re.compile(r"</?(?:div|p|li|h[1-6]|tr|br|section|ul|ol|table)\b[^>]*>", re.I)


def slides_text(ed, raw):
    """The deck as Markdown, for crawlers and LLMs: one heading per slide, its visible text below.
    Slide 1 is drawn in the Secession lettering (SVG paths), so its text comes from the edition."""
    secs = re.findall(r'<section class="slide" data-name="([^"]+)"[^>]*>(.*?)</section>', raw, re.S)
    part_of = {n: p for p, sl in ed["slides"] for _, n in sl}
    s = ed["start"]
    out = [f"# WAISS {ed['edition']} – slides", "",
           f"Wiener AI Software Stammtisch · {s:%a} {s.day} {s:%b %Y}, {s:%H:%M} · {ed['ort_lang']}, {ed['adresse']}", "",
           f"Present: {SITE}/{ed['slug']}/" + (f" · PDF: {SITE}/{ed['slug']}/waiss-{ed['slug']}-slides.pdf" if ed.get("pdf") else ""),
           f"Source: {REPO}", ""]
    part = None
    for k, (name, body) in enumerate(secs, 1):
        if part_of.get(name, part) != part:
            part = part_of.get(name, part)
            out += [f"## {part}", ""]
        body = re.sub(r"<(script|style|svg|video)\b[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
        body = BLOCK.sub("\n", body)
        text = html.unescape(re.sub(r"<[^>]+>", " ", body))
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.split("\n")]
        lines = [re.sub(r"\s*\[[a-z ]{1,16}\]", "", ln, flags=re.I) for ln in lines]  # placeholders like [xx min]
        lines = [ln for ln in lines if ln and not re.fullmatch(r"WAISS · #\d+( \d+( / \d+)?)?|\[[^\]]{1,24}\]", ln)]
        if k == 1:
            lines = [NAME, f"{ed['edition']} · {ed['datum']} · {ed['zeit']} · {ed['ort_lang']}"]
        out += [f"### {k:02d} · {name.split('-', 1)[1]}", "", *lines, ""]
    return "\n".join(out)


def git_date(*paths):
    """Date of the last commit touching these paths (needs full history: the workflow checks out with fetch-depth 0)."""
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%cs", "--", *paths], cwd=ROOT, capture_output=True, text=True)
        return r.stdout.strip() or None
    except OSError:
        return None


def sitemap(eds, today):
    deck_src = ("tools/deck.py", "tools/deck-template.html")
    home = max(filter(None, [git_date("editions", "tools/site.py", "tools/site.css", "tools/site.js")]
                      # the page changes on its own the day after an edition (upcoming -> past)
                      + [(e["start"] + timedelta(days=1)).date().isoformat() for e in eds if e["day"] < today]),
               default=today)
    urls = [(f"{SITE}/", home)]
    for e in eds:
        if e["slides"]:
            urls.append((f"{SITE}/{e['slug']}/", git_date(e["file"], *deck_src) or today))
            urls.append((f"{SITE}/editions/{e['slug']}/", git_date(e["file"], *deck_src) or today))
    urls.append((f"{SITE}/privacy/", git_date("tools/site.py") or today))
    rows = "".join(f"<url><loc>{u}</loc><lastmod>{min(d, today)}</lastmod></url>\n" for u, d in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{rows}</urlset>\n")


ROBOTS = f"""# WAISS – Wiener AI Software Stammtisch. Search engines and AI crawlers are welcome.
# A short summary for language models: {SITE}/llms.txt
User-agent: *
Allow: /

Sitemap: {SITE}/sitemap.xml
"""


def llms(eds, today, full_texts=None):
    """/llms.txt (llmstxt.org): the facts in a form language models can quote. With full_texts: /llms-full.txt."""
    up = [e for e in eds if e["day"] >= today]
    past = [e for e in eds if e["day"] < today][::-1]
    line = lambda e: (f"- WAISS {e['edition']}: {e['start']:%A} {e['start'].day} {e['start']:%B %Y}, {e['start']:%H:%M} "
                      f"(Vienna time), {e['ort_lang']}, {e['adresse']}"
                      + (f". Registration (free): {e['luma']}" if e["luma"] and e in up else "")
                      + (f". Slides: {SITE}/{e['slug']}/ (as text: {SITE}/{e['slug']}/slides.md)" if e["slides"] else ""))
    fmt = "\n".join(f"{k}. {html.unescape(t)} ({m}): {w}" for k, (t, w, m) in enumerate(FORMAT, 1))
    L = eds[-1]["links"]
    out = f"""# {NAME}

> {ABOUT}

The website and slides are in English; the name is Viennese German ("Stammtisch" = a regular get-together at a
café table). German: KI-Stammtisch in Wien.

## Facts

- What: a meetup for everyone who builds software with AI
- Where: Vienna, Austria; the venue is given per edition
- How often: about once a month
- Cost: free; registration on Luma
- Organizer: Telos Circle, a nonprofit in Vienna ({TELOS["website"]})
- Website: {SITE}/

## Every edition

{fmt}

## Upcoming

{chr(10).join(map(line, up)) or "- The next date is announced on the website and on Discord: " + L["discord"]}

## Past editions

{chr(10).join(map(line, past)) or "- none yet"}

## Links

- [Website]({SITE}/): editions and their slides
- [Source code and slides on GitHub]({REPO}): present at a future edition by opening a pull request
- [Discord]({L["discord"]}): community
- [Telos Circle]({TELOS["website"]}), [LinkedIn]({TELOS["linkedin"]}), [Instagram]({TELOS["instagram"]}), [X]({TELOS["x"]})
- Contact: events [at] teloscircle.com
"""
    if full_texts is None:
        return out + f"\n## Optional\n\n- [Full text of all slides]({SITE}/llms-full.txt)\n"
    demote = lambda t: re.sub(r"^#", "##", t, flags=re.M)  # each deck's title becomes a section of this file
    return out + "\n## Slides, as text\n\n" + "\n\n".join(map(demote, full_texts))


def og_crop(src, dst, w=OG_W, h=OG_H):
    """Centre crop to w:h, then scale (a 1920×1080 slide loses 36 px top and bottom for 1200×630)."""
    with Image.open(src) as im:
        im = im.convert("RGB")
        sw, sh = im.size
        cw, ch = (sw, round(sw * h / w)) if sw / sh < w / h else (round(sh * w / h), sh)
        box = ((sw - cw) // 2, (sh - ch) // 2, (sw - cw) // 2 + cw, (sh - ch) // 2 + ch)
        im.crop(box).resize((w, h), Image.LANCZOS).save(dst, quality=86, optimize=True, progressive=True)


# ------------------------------------------------------------------------------------- page
def page(title, desc, body, eds, prefix="", canonical=SITE + "/", robots=None, ld=None):
    css = (ROOT / "tools" / "site.css").read_text(encoding="utf-8")
    js = (ROOT / "tools" / "site.js").read_text(encoding="utf-8")
    blob = json.dumps({"fs": D.FS, "presets": R.PRESETS, "variant": D.VARIANT})
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{head(title, desc, canonical, prefix, robots=robots, ld=ld)}
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


def favicon(k=.62, stroke=16, rx=34):
    """The Secession W on a rounded tile. k = height of the W in the tile (of 1.0 = 100 units), stroke in glyph units.
    Small PNG sizes (tools/icons.js) use a bigger, bolder W so it stays readable at 16 px."""
    vx, w, d = R.G["W"]
    s = 100 + 2 * 26
    h = 100 * k
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}"><rect width="{s}" height="{s}" rx="{rx}" fill="#F5F3EE"/>'
            f'<g transform="translate({(s - w * k) / 2:.1f} {(s - h) / 2:.1f}) scale({k})"><path transform="translate({-vx} 0)" '
            f'd="{d}" fill="none" stroke="#1F1E1B" stroke-width="{stroke}"/></g></svg>')


# PNG icons rendered by tools/icons.js into assets/icons/ (committed; the W does not change):
# name: (px, favicon() arguments)
ICON_SPECS = {"icon-16": (16, dict(k=.86, stroke=24, rx=30)), "icon-32": (32, dict(k=.8, stroke=20, rx=32)),
              "icon-48": (48, dict(k=.74, stroke=18)), "apple-touch-icon": (180, dict(k=.62, rx=0)),
              "icon-192": (192, {}), "icon-512": (512, {})}


def build_icons():
    """favicon.ico, apple-touch-icon.png and the web manifest from the W icons in assets/icons/ (tools/icons.js)."""
    src = ROOT / "assets" / "icons"
    ICONS.clear()
    if not (src / "icon-32.png").exists():
        print("warning: assets/icons/ missing (npm run icons): only the SVG favicon")
        return
    (OUT / "icons").mkdir()
    for n in ("icon-192", "icon-512"):
        shutil.copy(src / f"{n}.png", OUT / "icons" / f"{n}.png")
    shutil.copy(src / "apple-touch-icon.png", OUT / "apple-touch-icon.png")  # browsers ask for /apple-touch-icon.png
    with Image.open(src / "icon-48.png") as big:
        small = [Image.open(src / f"icon-{px}.png") for px in (16, 32)]
        big.save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)], append_images=small)
    manifest = {"name": NAME, "short_name": "WAISS", "description": DESC, "start_url": "/", "display": "browser",
                "background_color": "#F5F3EE", "theme_color": "#F5F3EE",
                "icons": [{"src": f"/icons/icon-{px}.png", "sizes": f"{px}x{px}", "type": "image/png"} for px in (192, 512)]}
    (OUT / "site.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    ICONS.extend(['<link rel="icon" href="{p}favicon.ico" sizes="16x16 32x32 48x48">',
                  '<link rel="apple-touch-icon" href="{p}apple-touch-icon.png">',
                  '<link rel="manifest" href="{p}site.webmanifest">'])


def main():
    eds = load_editions()
    today = datetime.now(VIENNA).date().isoformat()
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "assets" / "fonts", OUT / "fonts")
    (OUT / "favicon.svg").write_text(favicon(), encoding="utf-8")
    build_icons()
    shutil.copy(ROOT / "assets" / "logo" / "telos-circle.svg", OUT / "telos-circle.svg")  # Organization logo (JSON-LD)
    for f in ("Dockerfile", "nginx.conf"):  # dist/ deploys as it is: Coolify builds this Dockerfile
        shutil.copy(ROOT / "deploy" / f, OUT / f)

    for ed in eds:
        d = OUT / ed["slug"]
        d.mkdir()
        if ed["slides"]:
            deck_html = (ROOT / "build" / ed["deck"] / "index.html").read_text(encoding="utf-8")
            if (ROOT / "build" / ed["deck"] / "media").exists():  # videos the deck fetches on click
                shutil.copytree(ROOT / "build" / ed["deck"] / "media", d / "media")
            png = ROOT / "exports" / ed["deck"]
            (d / "slides").mkdir()
            for _, sl in ed["slides"]:
                for _, n in sl:
                    src = png / f"{n}.png"
                    if not src.exists():
                        msg = f"{src} missing: run `npm run deck` again (the PNGs are older than the deck)"
                        if os.environ.get("CI"):
                            sys.exit(msg)
                        print("warning:", msg)  # local build while the deck is being edited
                        continue
                    with Image.open(src) as im:
                        im.convert("RGB").resize((960, 540), Image.LANCZOS).save(d / "slides" / f"{n}.webp", quality=82, method=6)
            pdf = png / "waiss-slides.pdf"
            ed["pdf"] = pdf.exists()
            if ed["pdf"]:
                shutil.copy(pdf, d / f'waiss-{ed["slug"]}-slides.pdf')
            (d / "slides.md").write_text(slides_text(ed, deck_html), encoding="utf-8")
        for t in ed.get("talks") or []:
            src = talk_src(t)
            if src and not t.get("url"):
                (d / "talks").mkdir(exist_ok=True)
                (shutil.copytree if t.get("html") else shutil.copy)(ROOT / src, d / "talks" / Path(src).name)

        # preview images: 1200×630 for link previews, 16:9 and 1:1 for the Event in JSON-LD
        title_png = ROOT / "exports" / (ed["deck"] or "-") / "01-titel.png"
        cover = ROOT / "exports" / f'{ed["num"]:03d}' / "luma-cover.png"
        ed["images"] = []
        if title_png.exists():
            og_crop(title_png, d / "og.jpg")
            og_crop(title_png, d / "cover-16x9.jpg", 1200, 675)
            ed["images"].append(f'{SITE}/{ed["slug"]}/cover-16x9.jpg')
        elif cover.exists():
            og_crop(cover, d / "og.jpg")
        if cover.exists():
            og_crop(cover, d / "cover-1x1.jpg", 1080, 1080)
            ed["images"].append(f'{SITE}/{ed["slug"]}/cover-1x1.jpg')
        if ed["slides"]:  # after the PDF check: the head and slides.md link to it
            (d / "index.html").write_text(deck_page(deck_html, ed), encoding="utf-8")
    latest = next((OUT / e["slug"] / "og.jpg" for e in eds[::-1] if (OUT / e["slug"] / "og.jpg").exists()), None)
    if latest:
        shutil.copy(latest, OUT / "og.jpg")
    for e in eds:
        e["images"] = e["images"] or [f"{SITE}/og.jpg"]

    master = ROOT / "build" / "master" / "index.html"
    if master.exists():
        (OUT / "master").mkdir()
        (OUT / "master" / "index.html").write_text(deck_page(master.read_text(encoding="utf-8"), master=True),
                                                  encoding="utf-8")

    body = hero() + editions(eds, today) + format_(eds, today) + slides(eds) + contribute(eds)
    (OUT / "index.html").write_text(page(f"{NAME} | AI meetup in Vienna", DESC, body, eds, ld=site_ld(eds)),
                                    encoding="utf-8")
    for e in eds:  # one page per edition with all its slides
        if has_slides(e):
            d = OUT / "editions" / e["slug"]
            d.mkdir(parents=True)
            (d / "index.html").write_text(page(
                f'WAISS {e["edition"]} – {e["start"]:%d %b %Y} – Slides',
                f'All slides of WAISS {e["edition"]} (Wiener AI Software Stammtisch), {e["start"].day} {e["start"]:%B %Y}, '
                f'{e["ort_lang"]}, Vienna: AI recap, show & tell, open round.',
                edition_page(e), eds, "../../", f'{SITE}/editions/{e["slug"]}/'), encoding="utf-8")
    (OUT / "privacy").mkdir()
    (OUT / "privacy" / "index.html").write_text(
        page("Privacy – WAISS", "Privacy policy of waiss.teloscircle.com: no cookies, no analytics, no tracking.",
             privacy(eds), eds, "../", SITE + "/privacy/"),
        encoding="utf-8")
    (OUT / "404.html").write_text(
        page("Not found – WAISS", DESC, '<section class="legal" data-cam="1.0,0.6,0,0" data-cam-m="0.6,0,0.3,0"><div class="wrap narrow">'
             '<div class="eyebrow">404</div><h2>Nothing here.</h2><p><a class="btn" href="/">Back to WAISS</a></p></div></section>',
             eds, "/", robots="noindex"), encoding="utf-8")

    (OUT / "robots.txt").write_text(ROBOTS, encoding="utf-8")
    (OUT / "sitemap.xml").write_text(sitemap(eds, today), encoding="utf-8")
    (OUT / "llms.txt").write_text(llms(eds, today), encoding="utf-8")
    texts = [(OUT / e["slug"] / "slides.md").read_text(encoding="utf-8") for e in eds[::-1] if e["slides"]]
    (OUT / "llms-full.txt").write_text(llms(eds, today, texts), encoding="utf-8")
    n = sum(1 for _ in OUT.rglob("*") if _.is_file())
    print(f"built {OUT} ({n} files, today {today} in Vienna)")


if __name__ == "__main__":
    main()
