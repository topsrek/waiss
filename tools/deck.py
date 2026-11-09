#!/usr/bin/env python3
"""Build the WAISS presentation: one self-contained HTML deck with ONE blob that only rotates and
travels between the slides (same shape the whole time, no morphing).

    python3 -X utf8 tools/deck.py editions/001.json     # -> build/deck/index.html
    node tools/export-deck.js                           # -> exports/deck/*.png + waiss-slides.pdf

Present: open build/deck/index.html, arrow keys / space / click (left third = back), F = fullscreen,
#N in the URL jumps to slide N. `index.html?print` is the static layout used for the PDF fallback.

Every layout is a function below returning (cam, html): cam = (zoom, shift-x, shift-y, rotation in degrees)
for the blob on that slide. Fill in the [placeholders]. Slide copy is English.
Categories for the recap (eyebrow above the title; the order is chronological): Releases, News, Drama.
Tweets: l_tweet, l_tweets, l_tweet_media render static cards in the WAISS look (no embed widget); fill name,
handle, text, and optionally avatar= / media= (image path) in tweet_card().
"""
import base64, json, math, re, sys
from pathlib import Path

import qrcode

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render as R  # noqa: E402

ROOT = R.ROOT
INK, MUTED = R.INK, "#66635C"
TILE_BG = "#FCFBF8"
GRAD = "linear-gradient(160deg, #F9F8F4 0%, #F5F3EE 48%, #EDEAE2 100%)"
VARIANT = 0  # the one blob shape used on every slide
FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,100..900'
         '&family=IBM+Plex+Mono:wght@400;500&family=Tektur:wght@400..900&family=Space+Grotesk:wght@700&family=Chakra+Petch:wght@600;700&display=swap">')
CORNER = 80  # distance of header / logo from the slide edge


# ------------------------------------------------------------------------------------- helpers
def data_uri(path, mime, fill=None):
    raw = (ROOT / path).read_bytes()
    if fill:  # simple-icons have no fill attribute
        raw = raw.replace(b"<path ", f'<path fill="{fill}" '.encode(), 1)
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def logo(name, style, cls="abs"):
    return f'<img class="{cls}" src="{data_uri(f"assets/logo/{name}.svg", "image/svg+xml")}" alt="Telos Circle" style="{style}">'


def qr_art(data, icon=None):
    """QR code as dots with softly rounded 'eyes'; optional logo in a round, knocked-out centre.
    Radius 5.5 modules is the largest centre that still decodes reliably (tested with OpenCV, also downscaled)."""
    q = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_H)
    q.add_data(data)
    q.make(fit=True)
    m, n = q.modules, len(q.modules)
    c0, R = n / 2, (min(5.5, n * 0.17) if icon else 0)
    eyes = [(0, 0), (n - 7, 0), (0, n - 7)]
    in_eye = lambda x, y: any(ex <= x < ex + 7 and ey <= y < ey + 7 for ex, ey in eyes)
    in_logo = lambda x, y: icon and math.hypot(x + .5 - c0, y + .5 - c0) < R + .5
    dots = "".join(f'<circle cx="{x + .5}" cy="{y + .5}" r=".45"/>' for y, row in enumerate(m)
                   for x, on in enumerate(row) if on and not in_eye(x, y) and not in_logo(x, y))
    eye = "".join(f'<rect x="{ex + .5}" y="{ey + .5}" width="6" height="6" rx=".7" fill="none" stroke="{INK}" stroke-width="1"/>'
                  f'<rect x="{ex + 2}" y="{ey + 2}" width="3" height="3" rx=".8"/>' for ex, ey in eyes)
    mid = ""
    if icon:
        s = R * 1.42
        mid = (f'<circle cx="{c0}" cy="{c0}" r="{R}" fill="{TILE_BG}" stroke="{INK}" stroke-width=".16"/>'
               f'<image href="{icon}" x="{c0 - s / 2}" y="{c0 - s / 2}" width="{s}" height="{s}"/>')
    return f'<svg viewBox="0 0 {n} {n}" role="img" aria-label="QR {data}"><g fill="{INK}">{dots}{eye}</g>{mid}</svg>'


def qr_tile(data, label, text, icon=None, size=290, side=False):
    if data:
        tile = f'<div class="tile">{qr_art(data, icon)}</div>'
    else:
        tile = '<div class="tile ph"><span class="mono">[QR]</span></div>'
    cap = (f'<div><div class="eyebrow" style="font-size:20px;margin-bottom:6px">{label}</div>'
           f'<div class="u">{text}</div></div>')
    flow = "flex-direction:row;align-items:center;width:auto;gap:44px;" if side else ""
    return f'<div class="qr" style="--s:{size}px;{flow}">{tile}{cap}</div>'


def chrome(i, n, ed, with_logo=True):
    return (f'<div class="abs mono" style="left:{CORNER}px;top:{CORNER - 24}px;right:{CORNER}px;display:flex;'
            f'justify-content:space-between;font-size:22px"><span>WAISS · {ed["edition"]}</span><span>{i:02d} / {n:02d}</span></div>'
            + (logo("telos-circle-by", f"right:{CORNER}px;bottom:{CORNER - 24}px;height:40px") if with_logo else ""))


def wifi_payload(w):
    esc = lambda s: re.sub(r'([\\;,:"])', r"\\\1", s)
    return f'WIFI:T:WPA;S:{esc(w["ssid"])};P:{esc(w["password"])};;'


def eyebrow(text, extra=""):
    return f'<div class="eyebrow" style="{extra}">{text}</div>'


def tweet_card(name, handle, text, meta="[10:42 · 3 Oct 2026]", stats="[1.2K likes · 340 reposts]",
               width=1000, size=44, avatar=None, media=None, media_h=0):
    """Static tweet card. avatar / media: image path relative to the repo, or None for a placeholder."""
    img = lambda path: data_uri(path, "image/" + path.rsplit(".", 1)[-1].replace("jpg", "jpeg"))
    av = f'<img src="{img(avatar)}" alt="">' if avatar else '<span class="mono" style="font-size:20px">[@]</span>'
    x = data_uri("assets/logo/x.svg", "image/svg+xml", INK)
    med = ""
    if media_h:
        inner = f'<img src="{img(media)}" alt="">' if media else '<span class="mono" style="font-size:22px">[Image / screenshot]</span>'
        med = f'<div class="media" style="height:{media_h}px">{inner}</div>'
    return (f'<div class="tw" style="width:{width}px"><div class="head"><div class="av">{av}</div>'
            f'<div class="who"><b>{name}</b><span>{handle}</span></div><img class="x" src="{x}" alt="X"></div>'
            f'<div class="body" style="font-size:{size}px">{text}</div>{med}'
            f'<div class="foot"><span>{meta}</span><span>{stats}</span></div></div>')


# The original shader shortens spikes that point at the camera, so the shape changed while the blob rotated.
# Here the spike length is fixed in object space: rotation is then the only thing that moves.
_FACING = "float facing = dot(unorient(n), normalize(vec3(0.0, 0.35, 4.6)));"
assert _FACING in R.FS
FS = R.FS.replace(_FACING, "float facing = dot(vec3(n.x, 0.9394 * n.y + 0.3429 * n.z, -0.3429 * n.y + 0.9394 * n.z), "
                           "normalize(vec3(0.0, 0.35, 4.6)));")


# ------------------------------------------------------------------------------------ layouts
def hack_chip(text, font, bg, fg, size=34):
    """A hackathon as a mention only: its own typeface and colours, no artwork, no dates."""
    return (f'<div style="font-family:{font};font-weight:700;font-size:{size}px;line-height:1;letter-spacing:.02em;'
            f'background:{bg};color:{fg};padding:22px 34px;border-radius:18px">{text}</div>')


def l_orga(ed):
    w = ed.get("wifi")
    wlan = (qr_tile(wifi_payload(w), "WLAN", f'{w["ssid"]}<br>{w["password"]}', size=400) if w
            else qr_tile(None, "WLAN", "[Network]<br>[Password]", size=400))
    ln = qr_tile(ed["links"]["linkedin"], "LinkedIn", "/in/pwimberger",
                 data_uri("assets/logo/linkedin.svg", "image/svg+xml", INK), 200, side=True)
    photo = data_uri("assets/people/peter.webp", "image/webp")
    html = (
        # Telos Circle + its hackathons
        logo("telos-circle-wortmarke", "left:120px;top:190px;height:100px")
        + '<div class="abs" style="left:120px;top:326px;width:1200px;font-size:36px;line-height:1.35">'
          'Vienna-based nonprofit fostering interdisciplinary innovation across science, technology and entrepreneurship. '
          'Home of the WAISS.</div>'
        + f'<div class="abs eyebrow" style="left:120px;top:462px">Hackathons</div>'
        + '<div class="abs" style="left:120px;top:516px;display:flex;gap:28px">'
        + hack_chip("OpenClaw HACK_001", "'Space Grotesk',sans-serif", "#0A0A0A", "#CCFF00")
        + hack_chip("HACK_002", "'Chakra Petch',sans-serif", "#070D11", "#35F39A")
        + '</div>'
        # Peter, with his LinkedIn code at the same height as the photo
        + f'<img class="abs" src="{photo}" alt="Peter" style="left:130px;top:790px;width:160px;height:200px;object-fit:cover;'
          f'object-position:50% 20%;border-radius:26px;outline:2px solid {INK};outline-offset:8px;'
          f'filter:grayscale(1) contrast(1.06)">'
        + '<div class="abs" style="left:350px;top:786px;width:470px"><h2 style="font-size:50px">Peter Wimberger</h2>'
          '<div class="mono" style="font-size:22px;margin:10px 0 22px">@topsrek</div>'
          '<div class="eyebrow" style="font-size:18px;margin-bottom:6px">Projects</div>'
          '<div style="font-size:30px;font-weight:500">Intercortex, Machine Literacy</div></div>'
        + f'<div class="abs" style="left:870px;top:790px">{ln}</div>'
        + f'<div class="abs" style="left:1400px;top:190px">{wlan}</div>')
    return (0.7, 0.72, -0.58, 200), html


def l_agenda(ed):
    rows = [("01", "AI recap of the month", "20 min"), ("02", "Show &amp; Tell · short talks", "[xx min]"),
            ("03", "Open round &amp; questions", "open end")]
    r = "".join(f'<div class="row"><span class="n">{a}</span><span class="t">{b}</span><span class="d">{c}</span></div>'
                for a, b, c in rows)
    html = (f'<div class="abs" style="left:120px;top:200px;width:800px">{eyebrow("Agenda")}'
            f'<h2 style="font-size:120px;margin:36px 0 56px">Tonight</h2>{r}</div>')
    return (1.1, 0.62, 0.0, 340), html


def l_story(ed):
    """One story of the recap, in chronological order. The category (Releases / News / Drama) is the subtitle."""
    html = (f'<div class="abs" style="left:120px;top:200px;width:1150px">{eyebrow("Releases")}'
            f'<div style="font-family:\'Tektur\',sans-serif;font-weight:400;font-size:64px;line-height:1;color:{MUTED};margin-top:40px">[03 Oct]</div>'
            f'<h2 style="font-size:150px;margin-top:28px">[Headline of the story]</h2>'
            f'<div style="font-size:40px;margin-top:44px;color:{MUTED}">[One sentence of context]</div></div>')
    return (1.8, 0.85, -0.35, 140), html


def l_tweet(ed):
    card = tweet_card("[Name]", "[@handle]", "[The tweet, in full. Short enough to read from the back row.]", width=1060, size=50)
    html = (f'<div class="abs" style="left:120px;top:200px">{eyebrow("Drama")}</div>'
            f'<div class="abs" style="left:130px;top:290px">{card}</div>')
    return (1.2, 0.88, -0.1, 20), html


def l_tweets(ed):
    a = tweet_card("[Name]", "[@handle]", "[First tweet]", width=790, size=40)
    b = tweet_card("[Name]", "[@reply]", "[The reply, or the other side of it]", width=790, size=40)
    html = (f'<div class="abs" style="left:120px;top:200px">{eyebrow("Drama")}</div>'
            f'<div class="abs" style="left:130px;top:280px">{a}</div>'
            f'<div class="abs" style="left:1000px;top:340px">{b}</div>')
    return (0.5, 0.0, -0.5, 280), html


def l_tweet_media(ed):
    card = tweet_card("[Name]", "[@handle]", "[Tweet text with a screenshot or chart attached.]", width=900, size=40, media_h=300)
    html = (f'<div class="abs" style="left:120px;top:200px">{eyebrow("News")}</div>'
            f'<div class="abs" style="left:130px;top:280px">{card}</div>')
    return (1.1, 0.9, -0.2, 100), html


def l_drei(ed):
    cards = "".join(
        f'<div style="border-top:2px solid {INK};padding-top:22px;display:flex;flex-direction:column;gap:14px">'
        f'<span class="eyebrow" style="font-size:20px">{cat}</span>'
        f'<strong style="font-size:48px;font-weight:700">[Item {k}]</strong>'
        f'<span style="font-size:32px;color:{MUTED};line-height:1.3">[One sentence on why it matters]</span></div>'
        for k, cat in zip("ABC", ("Releases", "News", "Drama")))
    html = (f'<div class="abs" style="left:120px;top:200px;width:1100px">{eyebrow("Roundup")}'
            f'<h2 style="font-size:96px;margin-top:36px">[What changed in everyday work]</h2></div>'
            f'<div class="abs" style="left:120px;right:120px;top:560px;display:grid;'
            f'grid-template-columns:repeat(3,minmax(0,1fr));gap:56px">{cards}</div>')
    return (0.34, 0.68, -0.44, 240), html


def l_zahl(ed):
    html = (f'<div class="abs" style="left:100px;top:190px">{eyebrow("Number of the month", "margin-left:20px")}'
            f'<h2 style="font-size:360px;line-height:1;margin-top:10px">[73 %]</h2>'
            f'<div style="font-size:44px;margin:10px 0 0 20px;width:900px;line-height:1.25">'
            f'[What the number means, in one sentence]</div>'
            f'<div class="mono" style="font-size:20px;margin:28px 0 0 20px">Source: [link]</div></div>')
    return (1.15, 0.78, -0.2, 340), html


def l_talk(ed):
    html = (f'<div class="abs" style="left:120px;top:200px;width:900px">{eyebrow("Show &amp; Tell")}'
            f'<h2 style="font-size:96px;margin:36px 0 48px">[Talk title]</h2>'
            f'<div style="font-size:40px;font-weight:600">[Name]</div>'
            f'<div style="font-size:32px;color:{MUTED};margin-top:8px">[Role · @handle]</div></div>'
            f'<div class="abs" style="left:1100px;top:200px;width:700px;height:440px;border:2px solid {INK};'
            f'background:rgba(255,255,255,.55);display:flex;align-items:center;justify-content:center">'
            f'<span class="mono" style="font-size:24px">[Screenshot / demo]</span></div>')
    return (0.75, -0.72, -0.62, 70), html


def l_statement(ed):
    html = (f'<div class="abs" style="left:160px;right:160px;top:340px;text-align:center">'
            f'<h2 style="font-size:150px;line-height:.98">[One sentence that sticks.]</h2>'
            f'<div class="mono" style="font-size:24px;margin-top:48px;color:{INK}">— [Source]</div></div>')
    return (2.3, 0.0, -0.02, 150), html


def l_frage(ed):
    html = (f'<div class="abs" style="left:160px;right:160px;top:200px;text-align:center">{eyebrow("Open round")}'
            f'<h2 style="font-size:100px;line-height:1.02;margin-top:36px">What surprised you this month?</h2></div>')
    return (1.0, 0.0, -0.62, 240), html


def l_ende(ed):
    L = ed["links"]
    short = lambda u: u.replace("https://", "").rstrip("/")
    icon = lambda f, fill=INK: data_uri(f"assets/logo/{f}.svg", "image/svg+xml", fill if f != "telos-circle" else None)
    qrs = "".join(qr_tile(L[k], lab, short(L[k]), icon(ic), 360) for k, lab, ic in (
        ("telos", "Telos Circle · Links", "telos-circle"), ("discord", "Discord", "discord"),
        ("github", "Slides · GitHub", "github")))
    html = (f'<div class="abs" style="left:120px;top:190px"><h2 style="font-size:130px">See you next time.</h2></div>'
            f'<div class="abs" style="left:130px;top:400px;display:flex;gap:80px">{qrs}</div>'
            f'<div class="abs" style="left:120px;bottom:{CORNER + 20}px;font-size:56px;font-weight:500;letter-spacing:-.01em">'
            f'Want to present next time? Talk to <strong style="font-weight:700">Peter</strong>.</div>')
    return (1.0, 1.0, 0.0, 300), html


LAYOUTS = [("orga", l_orga), ("agenda", l_agenda), ("story", l_story), ("tweet", l_tweet), ("tweets", l_tweets),
           ("tweet-media", l_tweet_media), ("drei-spalten", l_drei), ("zahl", l_zahl), ("talk", l_talk),
           ("statement", l_statement), ("frage", l_frage), ("ende", l_ende)]


def title_slide(ed):
    """Slide 1 comes from the canvas source (Main.dc.html) minus its own blob; the top line is smaller
    and carries the Telos Circle logo on the right, all three lines share the same left edge."""
    vals = dict(R.DEFAULTS, edition=ed["edition"], datum=f'{ed["datum"]} · {ed["zeit"]}', ort=ed["ort"])
    page = R.render("Main.dc.html", 1920, 1080, vals)
    body = re.search(r"<body[^>]*>(.*?)<script>\nconst PRESETS", page, re.S).group(1)
    body, n = re.subn(r'<div style="position: absolute; left: 0; top: 0; width: 1920px; height: 1080px">\s*'
                      r'<canvas class="blob".*?</canvas>\s*</div>', "", body, flags=re.S)
    assert n == 1, "blob wrapper not found in Main.dc.html"
    body = body.replace("background: #F5F3EE", "background: transparent")
    header = (f'<div style="position:absolute;left:120px;right:120px;top:100px;display:flex;justify-content:space-between;'
              f'align-items:center">{R.txt("WIENER AI SOFTWARE STAMMTISCH", 38)}'
              f'{logo("telos-circle-by", "height:40px", cls="")}</div>')
    body, n = re.subn(r'<div style="position: absolute; left: 120px; top: 100px">\s*<div style="display:flex.*?</div>\s*</div>',
                      lambda m: header, body, count=1, flags=re.S)
    assert n == 1, "header not found in Main.dc.html"
    body, n = re.subn(r"left: 100px; top: 300px", f"left: {TITLE_X}px; top: 300px", body, count=1)
    assert n == 1, "WAISS block not found in Main.dc.html"
    return (1.25, 0.55, 0.05, 0), body


TITLE_X = 120  # ink of the W starts exactly at the 120px edge shared with the other two lines


def main():
    ed = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "editions" / "001.json").read_text(encoding="utf-8"))
    n = len(LAYOUTS) + 1
    secs, names = [], []

    def add(name, cam, html):
        secs.append(f'<section class="slide" data-name="{name}" data-cam="{",".join(map(str, cam))}">{html}</section>')
        names.append(name)

    cam, html = title_slide(ed)
    add("01-titel", cam, html)
    for k, (name, fn) in enumerate(LAYOUTS, start=2):
        cam, html = fn(ed)
        add(f"{k:02d}-{name}", cam, html + chrome(k, n, ed, with_logo=name != "orga"))

    tpl = (ROOT / "tools" / "deck-template.html").read_text(encoding="utf-8")
    out = tpl
    for key, val in {"__TITLE__": f'WAISS {ed["edition"]} – Slides', "__FONTS__": FONTS, "__INK__": INK, "__MUTED__": MUTED,
                     "__GRAD__": GRAD, "__SLIDES__": "\n".join(secs), "__FS__": FS, "__TILE__": TILE_BG,
                     "__VARIANT__": str(VARIANT), "__PRESETS__": json.dumps(R.PRESETS)}.items():
        out = out.replace(key, val)
    dest = ROOT / "build" / "deck"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "index.html").write_text(out, encoding="utf-8")
    (dest / "meta.json").write_text(json.dumps({"slides": names}), encoding="utf-8")
    print(f"built {dest / 'index.html'} ({n} slides)")


if __name__ == "__main__":
    main()
