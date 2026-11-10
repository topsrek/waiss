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
from functools import partial
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


HEAD_TOP = 140  # eyebrow + title of every content slide start here
MODEL_PX = 112  # recap slides about a model: the model name is still the biggest thing on the slide
TITLE_PX = 68   # plain titles on content slides


def model_h(name, size=MODEL_PX, extra=""):
    return f'<h2 style="font-size:{size}px;line-height:.92;margin-top:16px;{extra}">{name}</h2>'


def subline(text, extra=""):
    return f'<div style="font-size:38px;font-weight:600;line-height:1.2;margin-top:10px;{extra}">{text}</div>' if text else ""


def tweet_card(name, handle, text, meta="[10:42 · 3 Oct 2026]",
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
            f'<div class="foot"><span>{meta}</span></div></div>')


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
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:800px">{eyebrow("Agenda")}'
            f'<h2 style="font-size:96px;margin:20px 0 56px">Tonight</h2>{r}</div>')
    return (1.1, 0.62, 0.0, 340), html


def l_website(ed, url="https://waiss.teloscircle.com", repo="https://github.com/topsrek/waiss",
              mail="events@teloscircle.com"):
    """The edition's website (slides, past editions) as a QR code, plus how to bring a talk next time.
    Links are real <a> elements: clicking one opens it instead of advancing the deck."""
    short = lambda u: u.replace("https://", "").rstrip("/")
    tel = data_uri("assets/logo/telos-circle.svg", "image/svg+xml")
    gh = data_uri("assets/logo/github.svg", "image/svg+xml", INK)
    env = (f'<svg viewBox="0 0 24 24" width="44" height="44" fill="none" stroke="{INK}" stroke-width="2" '
           f'stroke-linejoin="round"><rect x="2.5" y="5" width="19" height="14" rx="2.5"/><path d="M3 6.5l9 6.5 9-6.5"/></svg>')
    a = f'color:{INK};text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:8px'
    row = lambda icon, html: (f'<div style="display:flex;align-items:center;gap:26px;font-size:40px;font-weight:600;'
                              f'margin-top:34px">{icon}<span>{html}</span></div>')
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:1300px">{eyebrow("Slides &amp; website")}'
            f'<h2 style="font-size:{TITLE_PX}px;margin-top:16px"><a href="{url}" style="{a};text-decoration-thickness:4px">'
            f'{short(url)}</a></h2>'
            f'<div style="font-size:34px;color:{MUTED};margin-top:14px">Tonight&#8217;s slides, past and upcoming editions.</div></div>'
            f'<div class="abs" style="left:120px;top:420px">{qr_tile(url, "Website", short(url), tel, 400)}</div>'
            f'<div class="abs" style="left:700px;top:420px;width:1000px">'
            f'<h3 style="font-size:56px;font-weight:700;line-height:1.1;letter-spacing:-.01em">Want to present something next time?</h3>'
            + row(f'<img src="{gh}" alt="GitHub" style="width:44px;height:44px">',
                  f'Open a pull request on <a href="{repo}" style="{a}">{short(repo)}</a>')
            + row(env, f'or email <a href="mailto:{mail}" style="{a}">{mail}</a>')
            + f'<div class="mono" style="font-size:24px;margin-top:44px;color:{MUTED};line-height:1.4">'
              f'HTML preferred &#183; PPT and PDF work too</div></div>')
    return (0.42, 0.66, -0.55, 160), html


def l_story(ed, cat="Releases", date="[03 Oct]", head="[Headline of the story]", ctx="[One sentence of context]",
            head_size=120):
    """One story of the recap, in chronological order. The category (Releases / News / Drama) is the subtitle."""
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:1150px">{eyebrow(cat)}'
            f'<div style="font-family:\'Tektur\',sans-serif;font-weight:400;font-size:56px;line-height:1;color:{MUTED};margin-top:24px">{date}</div>'
            f'<h2 style="font-size:{head_size}px;margin-top:28px">{head}</h2>'
            f'<div style="font-size:40px;line-height:1.3;margin-top:44px;color:{MUTED}">{ctx}</div></div>')
    return (1.8, 0.85, -0.35, 140), html


def l_tweet(ed, cat="Drama", model=None, **card_kw):
    kw = dict(name="[Name]", handle="[@handle]", text="[The tweet, in full. Short enough to read from the back row.]",
              width=1060, size=50)
    card = tweet_card(**{**kw, **card_kw})
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px">{eyebrow(cat)}{model_h(model) if model else ""}</div>'
            f'<div class="abs" style="left:130px;top:{340 if model else 230}px">{card}</div>')
    return (1.2, 0.88, -0.1, 20), html


def l_tweets(ed):
    a = tweet_card("[Name]", "[@handle]", "[First tweet]", width=790, size=40)
    b = tweet_card("[Name]", "[@reply]", "[The reply, or the other side of it]", width=790, size=40)
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px">{eyebrow("Drama")}</div>'
            f'<div class="abs" style="left:130px;top:230px">{a}</div>'
            f'<div class="abs" style="left:1000px;top:290px">{b}</div>')
    return (0.5, 0.0, -0.5, 280), html


def l_tweet_media(ed, cat="News", model=None, **card_kw):
    kw = dict(name="[Name]", handle="[@handle]", text="[Tweet text with a screenshot or chart attached.]",
              width=900, size=40, media_h=300)
    card = tweet_card(**{**kw, **card_kw})
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px">{eyebrow(cat)}{model_h(model) if model else ""}</div>'
            f'<div class="abs" style="left:130px;top:{340 if model else 230}px">{card}</div>')
    return (1.1, 0.9, -0.2, 100), html


def l_drei(ed, cat="Roundup", head="[What changed in everyday work]", model=None,
           items=tuple((c, f"[Item {k}]", "[One sentence on why it matters]") for k, c in zip("ABC", ("Releases", "News", "Drama")))):
    cards = "".join(
        f'<div style="border-top:2px solid {INK};padding-top:22px;display:flex;flex-direction:column;gap:14px">'
        f'<span class="eyebrow" style="font-size:20px">{c}</span>'
        f'<strong style="font-size:48px;font-weight:700">{item}</strong>'
        f'<span style="font-size:32px;color:{MUTED};line-height:1.3">{why}</span></div>'
        for c, item, why in items)
    title = (model_h(model) + subline(head)) if model else f'<h2 style="font-size:{TITLE_PX}px;margin-top:16px">{head}</h2>'
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:1300px">{eyebrow(cat)}{title}</div>'
            f'<div class="abs" style="left:120px;right:120px;top:{430 if model else 340}px;display:grid;'
            f'grid-template-columns:repeat(3,minmax(0,1fr));gap:56px">{cards}</div>')
    return (0.34, 0.68, -0.44, 240), html


def l_zahl(ed, cat="Number of the month", num="[73 %]", text="[What the number means, in one sentence]", src="[link]",
           model=None):
    html = (f'<div class="abs" style="left:100px;top:{HEAD_TOP}px">{eyebrow(cat, "margin-left:20px")}'
            + (model_h(model, extra="margin-left:20px") if model else "")
            + f'<h2 style="font-size:{140 if model else 360}px;line-height:1;margin:{"36px 0 0 20px" if model else "10px 0 0"}">{num}</h2>'
            f'<div style="font-size:44px;margin:10px 0 0 20px;width:{1000 if model else 900}px;line-height:1.25">{text}</div>'
            f'<div class="mono" style="font-size:20px;margin:28px 0 0 20px">Source: {src}</div></div>')
    return (1.15, 0.78, -0.2, 340), html


def l_talk(ed):
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:900px">{eyebrow("Show &amp; Tell")}'
            f'<h2 style="font-size:{TITLE_PX}px;margin:16px 0 48px">[Talk title]</h2>'
            f'<div style="font-size:40px;font-weight:600">[Name]</div>'
            f'<div style="font-size:32px;color:{MUTED};margin-top:8px">[Role · @handle]</div></div>'
            f'<div class="abs" style="left:1100px;top:{HEAD_TOP}px;width:700px;height:440px;border:2px solid {INK};'
            f'background:rgba(255,255,255,.55);display:flex;align-items:center;justify-content:center">'
            f'<span class="mono" style="font-size:24px">[Screenshot / demo]</span></div>')
    return (0.75, -0.72, -0.62, 70), html


def l_statement(ed, text="[One sentence that sticks.]", src="[Source]", size=150, top=340, model=None):
    html = (f'<div class="abs" style="left:160px;right:160px;top:{top}px;text-align:center">'
            + (model_h(model, extra="margin:0 0 56px") if model else "")
            + f'<h2 style="font-size:{size}px;line-height:{1.1 if model else .98};font-weight:{600 if model else 800}">{text}</h2>'
            f'<div class="mono" style="font-size:24px;margin-top:48px;color:{INK}">— {src}</div></div>')
    return (2.3, 0.0, -0.02, 150), html


def l_frage(ed):
    html = (f'<div class="abs" style="left:160px;right:160px;top:200px;text-align:center">{eyebrow("Open round")}'
            f'<h2 style="font-size:100px;line-height:1.02;margin-top:36px">What surprised you this month?</h2></div>')
    return (1.0, 0.0, -0.62, 240), html


def l_fullscreen(ed, img="assets/recap/ai-tier-list.jpg", bg="#121214", credit="@SadAlbert10 on X"):
    """One image, as large as the slide allows (fit to height, centred) on a matching dark field; no chrome."""
    src = data_uri(img, "image/" + img.rsplit(".", 1)[-1].replace("jpg", "jpeg"))
    html = (f'<div class="abs" style="left:0;top:0;width:1920px;height:1080px;background:{bg};display:flex;'
            f'align-items:center;justify-content:center"><img src="{src}" alt="" style="max-width:100%;max-height:100%"></div>'
            f'<div class="abs mono" style="right:28px;bottom:24px;font-size:16px;color:#8A877F;'
            f'writing-mode:vertical-rl;transform:rotate(180deg)">{credit}</div>')
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


def l_bench(ed, cat="Benchmarks", head="[Headline]", panels=(), note="", hi=0, top=340, lab_w=190, model=None, width=None,
            cam=(0.28, 0.64, 0.34, 60)):
    """Small multiples of horizontal bars, one panel per benchmark.
    panels: (title, subtitle, [(model, value), ...][, {"max": 100, "fmt": "{:.1f}"}]); the scale runs 0..max per panel.
    Row `hi` of every panel is drawn in ink, the rest muted. Every bar carries its model name and value,
    so identity never depends on colour."""
    def panel(title, sub, rows, opt=None):
        opt = opt or {}
        top_v, fmt, row_h, bar_h = opt.get("max", 100), opt.get("fmt", "{:.1f}"), opt.get("row", 56), opt.get("bar", 34)
        r = "".join(
            f'<div style="display:grid;grid-template-columns:{lab_w}px 1fr;align-items:center;gap:18px;height:{row_h}px">'
            f'<span class="mono" style="font-size:19px;line-height:1.2;color:{INK if k == hi else MUTED};letter-spacing:.04em">{m}</span>'
            f'<div style="display:flex;align-items:center;gap:14px;border-left:2px solid {INK};height:100%">'
            f'<div style="width:{v / top_v * 72:.1f}%;height:{bar_h}px;border-radius:0 4px 4px 0;'
            f'background:{INK if k == hi else "#C9C5BB"}"></div>'
            f'<span style="font-size:{30 if k == hi else 24}px;font-weight:{700 if k == hi else 500};'
            f'color:{INK if k == hi else MUTED};font-variant-numeric:tabular-nums">{fmt.format(v)}</span></div></div>'
            for k, (m, v) in enumerate(rows))
        head = (f'<strong style="font-size:40px;font-weight:700;display:block">{title}</strong>'
                f'<span style="font-size:24px;color:{MUTED};display:block;margin:6px 0 26px">{sub}</span>') if title else ""
        return f'<div style="border-top:2px solid {INK};padding-top:{22 if title else 14}px">{head}{r}</div>'
    title = (model_h(model) + subline(head)) if model else f'<h2 style="font-size:{TITLE_PX}px;margin-top:16px">{head}</h2>'
    top = max(top, 430) if model else top
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:1300px">{eyebrow(cat)}{title}</div>'
            f'<div class="abs" style="left:120px;right:120px;top:{top}px;display:grid;'
            f'grid-template-columns:repeat({len(panels)},minmax(0,1fr));gap:64px;{"width:%dpx" % width if width else ""}">{"".join(panel(*p) for p in panels)}</div>'
            f'<div class="abs mono" style="left:120px;bottom:{CORNER + 4}px;width:1380px;font-size:19px;line-height:1.3;'
            f'letter-spacing:.04em">{note}</div>')
    return cam, html


def l_eci(ed, cat="Benchmarks · Epoch AI", model=None, head="", csv="assets/recap/eci_scores.csv", since="2025-11-10",
          hi="Claude Fable 5.2", label=(), note="", ymin=135, ymax=180):
    """Release date vs. Epoch Capabilities Index, drawn from Epoch's CSV (epoch.ai/data/eci_scores.csv) as inline SVG.
    Every model since `since` is a muted dot; a new record at release is an ink dot on the frontier step line.
    `label`: {display name: (dx, dy, text-anchor)} for the frontier points that get a direct label."""
    import csv as _csv
    from datetime import date
    rows = [r for r in _csv.DictReader((ROOT / csv).open(encoding="utf-8")) if r["eci"] and r["date"]]
    rows.sort(key=lambda r: (r["date"], -float(r["eci"])))
    d0, d1 = date.fromisoformat(since), max(date.fromisoformat(r["date"]) for r in rows)
    W, H, L, T, Rr, B = 1680, 470, 70, 20, 250, 50  # svg size and plot margins; the right margin holds the last label
    X = lambda d: L + (date.fromisoformat(d) - d0).days / (d1 - d0).days * (W - L - Rr)
    Y = lambda v: T + (ymax - v) / (ymax - ymin) * (H - T - B)
    best = max((float(r["eci"]) for r in rows if r["date"] < since), default=ymin)
    front, dots = [], []
    for r in rows:
        v = float(r["eci"])
        if r["date"] >= since:
            (front if v > best else dots).append(r)
        best = max(best, v)
    x_end = W - Rr + 40
    grid = "".join(f'<line x1="{L}" x2="{x_end}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#D9D5CC" stroke-width="1"/>'
                   f'<text x="{L - 16}" y="{Y(v) + 7:.1f}" text-anchor="end" class="ax">{v}</text>'
                   for v in range(140, ymax + 1, 10))
    months = "".join(f'<text x="{X(d):.1f}" y="{H - 12}" text-anchor="middle" class="ax">{lab}</text>'
                     f'<line x1="{X(d):.1f}" x2="{X(d):.1f}" y1="{H - B}" y2="{H - B + 8}" stroke="{INK}" stroke-width="2"/>'
                     for d, lab in (("2025-12-01", "DEC 25"), ("2026-03-01", "MAR 26"), ("2026-06-01", "JUN 26"),
                                    ("2026-09-01", "SEP 26"), ("2026-11-01", "NOV 26")))
    pts = [(X(r["date"]), Y(float(r["eci"]))) for r in front]
    path = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for (x0, y0), (x, y) in zip(pts, pts[1:]):
        path += f" L{x:.1f},{y0:.1f} L{x:.1f},{y:.1f}"
    muted = "".join(f'<circle cx="{X(r["date"]):.1f}" cy="{Y(float(r["eci"])):.1f}" r="7" fill="#C9C5BB"/>' for r in dots)
    ink = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{13 if r["Display name"] == hi else 8}" fill="{INK}" '
                  f'stroke="#F5F3EE" stroke-width="3"/>' for r, (x, y) in zip(front, pts))
    h = next(r for r in front if r["Display name"] == hi)
    ci = (f'<line x1="{X(h["date"]):.1f}" x2="{X(h["date"]):.1f}" y1="{Y(float(h["eci_ci_low"])):.1f}" '
          f'y2="{Y(min(float(h["eci_ci_high"]), ymax)):.1f}" stroke="{INK}" stroke-width="2"/>')
    labs = ""
    for r, (x, y) in zip(front, pts):
        if r["Display name"] not in label:
            continue
        big = r["Display name"] == hi
        name = r["Display name"].replace("Claude ", "")
        dx, dy, anchor = (30, 12, "start") if big else label[r["Display name"]]
        labs += (f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" '
                 f'text-anchor="{anchor}" class="{"lb hi" if big else "lb"}">'
                 f'{name} · {float(r["eci"]):.0f}</text>')
    svg = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" style="overflow:visible;display:block">'
           f'<style>.ax{{font:400 20px "IBM Plex Mono",monospace;fill:{MUTED};letter-spacing:.04em}}'
           f'.lb{{font:500 24px Archivo,sans-serif;fill:{MUTED}}}.lb.hi{{font-weight:700;font-size:36px;fill:{INK}}}</style>'
           f'{grid}<line x1="{L}" x2="{L}" y1="{T - 10}" y2="{H - B}" stroke="{INK}" stroke-width="2"/>'
           f'<line x1="{L}" x2="{x_end}" y1="{H - B}" y2="{H - B}" stroke="{INK}" stroke-width="2"/>{months}'
           f'{muted}<path d="{path}" fill="none" stroke="{INK}" stroke-width="2"/>{ci}{ink}{labs}</svg>')
    title = (model_h(model) + subline(head)) if model else f'<h2 style="font-size:{TITLE_PX}px;margin-top:16px">{head}</h2>'
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:1300px">{eyebrow(cat)}{title}</div>'
            f'<div class="abs" style="left:70px;top:420px">{svg}</div>'
            f'<div class="abs mono" style="left:120px;bottom:{CORNER + 4}px;width:1380px;font-size:19px;line-height:1.3;'
            f'letter-spacing:.04em">{note}</div>')
    return (0.28, 0.64, 0.34, 100), html


def l_tweet_video(ed, cat="Community", model=None, head="", video=None, poster=None, ratio=2.0, **card_kw):
    """Model name + subline + a small tweet card on the left, the tweet's video large on the right.
    The video is embedded (data URI); it plays muted and looped while its slide is shown, and its poster stands in
    for the PNG / PDF export."""
    kw = dict(name="[Name]", handle="[@handle]", text="[Tweet text]", width=580, size=28)
    card = tweet_card(**{**kw, **card_kw})
    vw = 1060
    vid = (f'<video class="clip" src="{data_uri(video, "video/mp4")}" poster="{data_uri(poster, "image/jpeg")}" '
           f'muted loop playsinline preload="auto" style="width:{vw}px;height:{vw / ratio:.0f}px;display:block;'
           f'border-radius:18px;outline:2px solid {INK};outline-offset:8px;background:#000"></video>')
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:600px">{eyebrow(cat)}{model_h(model) if model else ""}'
            f'{subline(head)}</div>'
            f'<div class="abs" style="left:130px;top:420px">{card}</div>'
            f'<div class="abs" style="left:{1800 - vw}px;top:380px">{vid}</div>')
    return (0.28, 0.64, 0.34, 140), html


def l_table(ed, cat="Benchmarks", model=None, head="", cols=(), rows=(), strong=(), note="", top=430, row_h=56,
            cam=(0.28, 0.64, 0.34, 60)):
    """A plain table for numbers people compare across a row. cols: [(label, width px, align)], rows: [[cell, ...]].
    Rows whose first cell is in `strong` are drawn in ink and bold, the rest muted; a row starting with None is a
    divider labelled by its second cell."""
    def cells(vals, style):
        return "".join(f'<div style="width:{w}px;text-align:{a};{style}">{v}</div>' for (_, w, a), v in zip(cols, vals))
    hdr = (f'<div class="mono" style="display:flex;gap:28px;font-size:19px;letter-spacing:.06em;color:{MUTED};'
           f'border-bottom:2px solid {INK};padding-bottom:12px">{cells([c[0] for c in cols], "")}</div>')
    body = ""
    for r in rows:
        if r[0] is None:
            body += (f'<div class="mono" style="font-size:17px;letter-spacing:.08em;color:{MUTED};padding:16px 0 4px;'
                     f'border-bottom:1px solid #D9D5CC">{r[1]}</div>')
            continue
        on = r[0] in strong
        body += (f'<div style="display:flex;gap:28px;align-items:center;height:{row_h}px;border-bottom:1px solid #D9D5CC;'
                 f'font-size:{30 if on else 26}px;font-weight:{700 if on else 500};color:{INK if on else MUTED};'
                 f'font-variant-numeric:tabular-nums">{cells(r, "")}</div>')
    title = (model_h(model) + subline(head)) if model else f'<h2 style="font-size:{TITLE_PX}px;margin-top:16px">{head}</h2>'
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:1300px">{eyebrow(cat)}{title}</div>'
            f'<div class="abs" style="left:120px;top:{top}px">{hdr}{body}</div>'
            f'<div class="abs mono" style="left:120px;bottom:{CORNER + 4}px;width:1380px;font-size:19px;line-height:1.3;'
            f'letter-spacing:.04em">{note}</div>')
    return cam, html


VALS_NAMES = {"anthropic/claude-fable-5-2": "Fable 5.2", "anthropic/claude-opus-5-5": "Opus 5.5",
              "anthropic/claude-sonnet-5-5": "Sonnet 5.5", "anthropic/claude-haiku-5-5": "Haiku 5.5",
              "google/gemini-4-carbon": "Gemini 4 Carbon", "google/gemini-4-argon": "Gemini 4 Argon",
              "meta/muse-wonder-full": "Muse Wonder Full", "meta/muse-ember": "Muse Ember",
              "openai/gpt-6-astra": "GPT-6 Astra", "openai/gpt-6.1-sol": "GPT-6.1 Sol", "openai/gpt-6.1-terra": "GPT-6.1 Terra",
              "openai/gpt-6-luna": "GPT-6 Luna", "deepseek/deepseek-v4.1-flash-1017": "DeepSeek V4.1 Flash"}


def vals_models(path="assets/recap/vals_index.json"):
    return {m["id"]: m for m in json.loads((ROOT / path).read_text(encoding="utf-8"))["models"] if m["accuracy"] and m["cost_per_test"]}


def l_pareto(ed, cat="Benchmarks · Vals AI", model=None, head="", hi="anthropic/claude-fable-5-2", label=None, note="",
             xmin=0.1, xmax=40, ymin=20, ymax=75):
    """Vals Index: accuracy vs. cost per task (log x), from assets/recap/vals_index.json. Muted dots for every model,
    the Pareto frontier (nothing both cheaper and better) as an ink step line. label: {model id: (dx, dy, anchor)}."""
    ms = vals_models()
    W, H, L, T, Rr, B = 1680, 470, 70, 20, 40, 50
    X = lambda c: L + (math.log10(c) - math.log10(xmin)) / (math.log10(xmax) - math.log10(xmin)) * (W - L - Rr)
    Y = lambda v: T + (ymax - v) / (ymax - ymin) * (H - T - B)
    pts = sorted(ms.values(), key=lambda m: (m["cost_per_test"], -m["accuracy"]))
    front, best = [], -1
    for m in pts:
        if m["accuracy"] > best:
            front.append(m); best = m["accuracy"]
    fid = {m["id"] for m in front}
    grid = "".join(f'<line x1="{L}" x2="{W - Rr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#D9D5CC" stroke-width="1"/>'
                   f'<text x="{L - 16}" y="{Y(v) + 7:.1f}" text-anchor="end" class="ax">{v}%</text>' for v in range(ymin, ymax + 1, 10))
    ticks = "".join(f'<text x="{X(c):.1f}" y="{H - 12}" text-anchor="middle" class="ax">${c:g}</text>'
                    f'<line x1="{X(c):.1f}" x2="{X(c):.1f}" y1="{H - B}" y2="{H - B + 8}" stroke="{INK}" stroke-width="2"/>'
                    for c in (0.1, 0.3, 1, 3, 10, 30))
    path = f"M{X(front[0]['cost_per_test']):.1f},{Y(front[0]['accuracy']):.1f}"
    for a, b in zip(front, front[1:]):
        path += f" L{X(b['cost_per_test']):.1f},{Y(a['accuracy']):.1f} L{X(b['cost_per_test']):.1f},{Y(b['accuracy']):.1f}"
    dots = ""
    for m in sorted(ms.values(), key=lambda m: (m["id"] in fid, m["id"] == hi)):
        x, y = X(m["cost_per_test"]), Y(m["accuracy"])
        on = m["id"] in fid or m["id"] in (label or {})
        r = 13 if m["id"] == hi else 8 if on else 7
        if m["id"] == hi or m["id"] in (label or {}):
            e = m["stderr"]
            dots += f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{Y(m["accuracy"] + e):.1f}" y2="{Y(m["accuracy"] - e):.1f}" stroke="{INK}" stroke-width="2"/>'
        dots += (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{INK if on else "#C9C5BB"}"'
                 + (f' stroke="#F5F3EE" stroke-width="3"/>' if on else '/>'))
    labs = ""
    for mid, (dx, dy, anchor) in (label or {}).items():
        m = ms[mid]
        big = mid == hi
        labs += (f'<text x="{X(m["cost_per_test"]) + dx:.1f}" y="{Y(m["accuracy"]) + dy:.1f}" text-anchor="{anchor}" '
                 f'class="{"lb hi" if big else "lb"}">{VALS_NAMES.get(mid, mid)} · {m["accuracy"]:.1f}%</text>')
    svg = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" style="overflow:visible;display:block">'
           f'<style>.ax{{font:400 20px "IBM Plex Mono",monospace;fill:{MUTED};letter-spacing:.04em}}'
           f'.lb{{font:500 24px Archivo,sans-serif;fill:{MUTED}}}.lb.hi{{font-weight:700;font-size:34px;fill:{INK}}}</style>'
           f'{grid}<line x1="{L}" x2="{L}" y1="{T - 10}" y2="{H - B}" stroke="{INK}" stroke-width="2"/>'
           f'<line x1="{L}" x2="{W - Rr}" y1="{H - B}" y2="{H - B}" stroke="{INK}" stroke-width="2"/>{ticks}'
           f'<path d="{path}" fill="none" stroke="{INK}" stroke-width="2"/>{dots}{labs}'
           f'<text x="{W - Rr}" y="{H - B - 14}" text-anchor="end" class="ax">COST PER TASK, LOG SCALE &#8594;</text></svg>')
    title = (model_h(model) + subline(head)) if model else f'<h2 style="font-size:{TITLE_PX}px;margin-top:16px">{head}</h2>'
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:1300px">{eyebrow(cat)}{title}</div>'
            f'<div class="abs" style="left:70px;top:420px">{svg}</div>'
            f'<div class="abs mono" style="left:120px;bottom:{CORNER + 4}px;width:1380px;font-size:19px;line-height:1.3;'
            f'letter-spacing:.04em">{note}</div>')
    return (0.28, 0.64, 0.34, 20), html


def vals_rows(ids):
    ms = vals_models()
    def dur(s):  # rounded like vals.ai: "1h 25m" / "43m 42s"
        s = round(s)
        return f"{s // 3600}h {round(s % 3600 / 60):02d}m" if s >= 3600 else f"{s // 60}m {s % 60:02d}s"
    return [[VALS_NAMES[i], f'{ms[i]["accuracy"]:.1f}%', f'${ms[i]["cost_per_test"]:.2f}', f'{ms[i]["tokens_per_test"] / 1e6:.1f}M',
             dur(ms[i]["latency_s"])] for i in ids]


LABS = {"Anthropic": "Anthropic", "OpenAI": "OpenAI", "Google DeepMind": "Google", "Google": "Google",
        "Google DeepMind,Google": "Google", "Meta AI": "Meta"}


def eci_rows(csv="assets/recap/eci_scores.csv"):
    import csv as _csv
    rows = [r for r in _csv.DictReader((ROOT / csv).open(encoding="utf-8")) if r["eci"] and r["date"]]
    for r in rows:
        r["lab"], r["v"] = LABS.get(r["Organization"]), float(r["eci"])
    return sorted(rows, key=lambda r: r["date"])


def _chart_frame(W, H, html_chart, question, note, cat="Discussion", top=330):
    return (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:1500px">{eyebrow(cat)}'
            f'<h2 style="font-size:64px;line-height:1.02;margin-top:16px">{question}</h2></div>'
            f'<div class="abs" style="left:120px;top:{top}px">{html_chart}</div>'
            f'<div class="abs mono" style="left:120px;bottom:{CORNER + 4}px;width:1380px;font-size:19px;line-height:1.3;'
            f'letter-spacing:.04em">{note}</div>')


def _x_axis(X, H, B, L, W):
    from datetime import date
    return "".join(f'<text x="{X(d):.1f}" y="{H - 12}" text-anchor="middle" class="ax">{lab}</text>'
                   f'<line x1="{X(d):.1f}" x2="{X(d):.1f}" y1="{H - B}" y2="{H - B + 8}" stroke="{INK}" stroke-width="2"/>'
                   for d, lab in (("2025-12-01", "DEC 25"), ("2026-03-01", "MAR 26"), ("2026-06-01", "JUN 26"),
                                  ("2026-09-01", "SEP 26"), ("2026-11-01", "NOV 26"))) + \
        f'<line x1="{L}" x2="{W}" y1="{H - B}" y2="{H - B}" stroke="{INK}" stroke-width="2"/>'


_STYLE = (f'<style>.ax{{font:400 20px "IBM Plex Mono",monospace;fill:{MUTED};letter-spacing:.04em}}'
          f'.lb{{font:700 30px Archivo,sans-serif;fill:{INK}}}.lb.m{{fill:{MUTED}}}'
          f'.sm{{font:500 22px Archivo,sans-serif;fill:{MUTED}}}</style>')


def l_cadence(ed, question="", since="2025-11-10", until="2026-11-10", bands=(), note="", labs=("Anthropic", "OpenAI", "Google", "Meta")):
    """Release cadence: one row per lab, a dot per model release (Epoch's list); filled ink = new best of that lab,
    hollow = any other release. bands: [(from, to, label)] shaded date ranges where several labs shipped at once."""
    from datetime import date
    rows = eci_rows()
    W, H, L, Rr, B, row = 1680, 560, 170, 250, 50, 118
    d0, d1 = date.fromisoformat(since), date.fromisoformat(until)
    X = lambda d: L + (date.fromisoformat(d) - d0).days / (d1 - d0).days * (W - L - Rr)
    out = ""
    for f, t, lab, anchor in bands:
        out += (f'<rect x="{X(f) - 8:.1f}" y="0" width="{X(t) - X(f) + 16:.1f}" height="{H - B}" fill="#E4E0D7" rx="6"/>'
                f'<text x="{X(f) - 18 if anchor == "end" else X(t) + 18:.1f}" y="24" text-anchor="{anchor}" class="sm">{lab}</text>')
    for k, lab in enumerate(labs):
        y = 50 + row * k + row / 2
        best, n, rec = max((r["v"] for r in rows if r["lab"] == lab and r["date"] < since), default=0), 0, 0
        out += (f'<line x1="{L}" x2="{W - Rr + 20}" y1="{y:.1f}" y2="{y:.1f}" stroke="#D9D5CC" stroke-width="1"/>'
                f'<text x="0" y="{y + 10:.1f}" class="lb">{lab}</text>')
        for r in rows:
            if r["lab"] != lab:
                continue
            if since <= r["date"] <= until:
                n += 1
                new = r["v"] > best
                rec += new
                out += (f'<circle cx="{X(r["date"]):.1f}" cy="{y:.1f}" r="{11 if new else 8}" '
                        + (f'fill="{INK}"/>' if new else f'fill="#F5F3EE" stroke="{MUTED}" stroke-width="3"/>'))
            best = max(best, r["v"])
        out += (f'<text x="{W - Rr + 50}" y="{y + 2:.1f}" class="lb" style="font-size:28px">{n} releases</text>'
                f'<text x="{W - Rr + 50}" y="{y + 30:.1f}" class="sm">{rec} new lab bests</text>')
    svg = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" style="overflow:visible;display:block">{_STYLE}'
           f'{out}{_x_axis(X, H, B, L, W - Rr + 20)}</svg>')
    return (0.28, 0.64, 0.34, 220), _chart_frame(W, H, svg, question, note)


def l_labs(ed, question="", since="2025-11-10", until="2026-11-10", note="", ymin=130, ymax=178, top=330,
           labs=(("Anthropic", 5, None), ("OpenAI", 5, "12 7"), ("Google", 3, None), ("Meta", 3, "12 7"))):
    """Each lab's best Epoch Capabilities Index score so far, as a step line per lab; labelled at the right end with
    the gap to the leader. labs: (name, stroke width, dash) - ink for the first two, muted for the rest."""
    from datetime import date
    rows = eci_rows()
    W, H, L, T, Rr, B = 1680, 560 - (top - 330), 70, 10, 330, 50
    d0, d1 = date.fromisoformat(since), date.fromisoformat(until)
    X = lambda d: L + (date.fromisoformat(d) - d0).days / (d1 - d0).days * (W - L - Rr)
    Y = lambda v: T + (ymax - v) / (ymax - ymin) * (H - T - B)
    grid = "".join(f'<line x1="{L}" x2="{W - Rr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#D9D5CC" stroke-width="1"/>'
                   f'<text x="{L - 16}" y="{Y(v) + 7:.1f}" text-anchor="end" class="ax">{v}</text>' for v in range(ymin, ymax + 1, 10))
    ends, out = {}, ""
    for k, (lab, sw, dash) in enumerate(labs):
        best = max((r["v"] for r in rows if r["lab"] == lab and r["date"] < since), default=None)
        pts = [(since, best)] if best else []
        for r in rows:
            if r["lab"] == lab and since <= r["date"] <= until and (best is None or r["v"] > best):
                best = r["v"]; pts.append((r["date"], best))
        d = f"M{X(pts[0][0]):.1f},{Y(max(pts[0][1], ymin)):.1f}"
        for (_, v0), (dt, v) in zip(pts, pts[1:]):
            d += f" L{X(dt):.1f},{Y(max(v0, ymin)):.1f} L{X(dt):.1f},{Y(v):.1f}"
        d += f" L{W - Rr:.1f},{Y(pts[-1][1]):.1f}"
        col = INK if k < 2 else MUTED
        out += (f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{sw}"'
                + (f' stroke-dasharray="{dash}"' if dash else "") + '/>')
        ends[lab] = (pts[-1][1], col)
    lead = max(v for v, _ in ends.values())
    ys = sorted(((v, lab) for lab, (v, _) in ends.items()), reverse=True)
    last = -1e9
    for v, lab in ys:  # push end labels apart so they never overlap
        y = max(Y(v) + 10, last + 40)
        last = y
        gap = "#1" if v == lead else f"&#8722;{lead - v:.0f}"
        out += (f'<text x="{W - Rr + 24}" y="{y:.1f}" class="lb{" m" if ends[lab][1] == MUTED else ""}">{lab}</text>'
                f'<text x="{W - Rr + 200}" y="{y:.1f}" class="lb{" m" if ends[lab][1] == MUTED else ""}" '
                f'style="font-weight:500">{v:.0f} <tspan class="sm">{gap}</tspan></text>')
    svg = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" style="overflow:visible;display:block">{_STYLE}{grid}'
           f'<line x1="{L}" x2="{L}" y1="0" y2="{H - B}" stroke="{INK}" stroke-width="2"/>{out}{_x_axis(X, H, B, L, W - Rr)}</svg>')
    return (0.28, 0.64, 0.34, 260), _chart_frame(W, H, svg, question, note, top=top)


# ----------------------------------------------------------------- recap #1: Meta Muse Ember (09 Nov 2026)
MUSE_SRC = "x.com/ArtificialAnlys/status/2119854348587123007"
MUSE = [
    ("muse-tweet", partial(
        l_tweet, cat="Releases · Meta · 09 Nov", model="Muse Ember", size=40, name="Artificial Analysis", handle="@ArtificialAnlys",
        avatar="assets/recap/artificialanlys-avatar.jpg",
        text="Meta&#8217;s newest model Muse Ember scores 36 on the Artificial Analysis Intelligence Index, "
             "matching Claude Haiku 5.5 (max) at a third of the Cost per Task",
        meta="19:07 · 9 Nov 2026")),
    ("muse-bench", partial(
        l_bench, cat="Releases · Meta", model="Muse Ember", head="Haiku-level, at a third of the cost", lab_w=250,
        panels=[("Intelligence Index", "Artificial Analysis, max effort",
                 [("Muse Ember", 36), ("Claude Haiku 5.5", 36), ("DeepSeek V4.1 Flash", 33), ("GLM-5.3-Flash", 28)],
                 {"max": 60, "fmt": "{:.0f}"}),
                ("Cost per task", "USD per index task, lower is better",
                 [("Muse Ember", 0.14), ("Claude Haiku 5.5", 0.41), ("DeepSeek V4.1 Flash", 0.60), ("GLM-5.3-Flash", 0.58)],
                 {"max": 0.7, "fmt": "${:.2f}"}),
                ("Coding Agent Index", "In Muse Code / Claude Code / Codex",
                 [("Muse Ember", 46), ("Claude Haiku 5.5", 37), ("GPT-6 Luna", 31)],
                 {"max": 60, "fmt": "{:.0f}"})],
        note=f"$0.10 / $0.50 per 1M tokens in / out. Weak spot: knowledge (AA-Omniscience 21% vs. 35% for Haiku), "
             f"it declines 64% of questions but hallucinates half as often. Source: {MUSE_SRC}")),
]


# ----------------------------------------------------------------- recap #2: Claude Fable 5.2 (09 Nov 2026)
FABLE_SRC = "anthropic.com/claude-fable-and-mythos-5-2"
AA_SRC = "artificialanalysis.ai, 10 Nov 2026"
ECI_SRC = "epoch.ai/eci, eci_scores.csv of 10 Nov 2026"
VALS_SRC = "vals.ai/benchmarks/vals_index, v2.2 of 9 Nov 2026"
FABLE = [
    ("fable-tweet", partial(
        l_tweet_media, cat="Releases · Anthropic", model="Fable 5.2", name="Claude", handle="@claudeai", avatar="assets/recap/claudeai-avatar.jpg",
        text="Introducing Claude Fable 5.2 and Claude Mythos 5.2, designed to tackle the most daunting technical challenges.",
        media="assets/recap/fable-5-2-video.jpg", media_h=150, width=1150, size=34,
        meta="19:57 · 9 Nov 2026")),
    ("fable-bench", partial(
        l_bench, cat="Releases · Anthropic", model="Fable 5.2", head="Ahead almost everywhere, 20% cheaper than 5.1",
        panels=[("FrontierSWE v2", "Agentic coding",
                 [("Fable 5.2", 69.9), ("GPT-6 Astra", 65.5), ("Opus 5.5", 62.3), ("Fable 5.1", 56.3)]),
                ("Humanity&#8217;s Last Exam", "Expert questions, with tools",
                 [("Fable 5.2", 74.2), ("Opus 5.5", 67.7), ("Fable 5.1", 65.6), ("GPT-6 Astra", 57.2)]),
                ("RoboDojo Sim", "Robot control in simulation",
                 [("Fable 5.2", 64.9), ("Opus 5.5", 39.4), ("GPT-6 Astra", 29.8), ("Fable 5.1", 27.6)])],
        note=f"Score in %, vendor-reported, highest effort per model. Gemini 4 Carbon leads AutomationBench "
             f"(53.9 vs 51.4). Source: {FABLE_SRC}")),
    ("fable-aa", partial(
        l_bench, cat="Benchmarks · Artificial Analysis", model="Fable 5.2", head="New #1 on the Intelligence Index",
        lab_w=300, width=1150, top=430, cam=(0.42, 0.66, -0.08, 200),
        panels=[(None, None,
                 [("Claude Fable 5.2", 64.6), ("Gemini 4 Carbon", 60.0), ("Claude Opus 5.5", 59.1), ("GPT-6 Astra", 56.9),
                  ("GPT-6.1 Sol", 54.6), ("Claude Sonnet 5.5", 54.5), ("Muse Wonder Full", 50.1), ("Claude Fable 5.1", 49.2)],
                 {"max": 70, "fmt": "{:.0f}", "row": 54, "bar": 32})],
        note=f"Index v5.0.1, measured independently, highest effort per model. Fable 5.1 &#8594; 5.2: +15 points in ten weeks. "
             f"Source: {AA_SRC}")),
    ("fable-eci", partial(
        l_eci, model="Fable 5.2", head="Biggest jump of the year on Epoch&#8217;s Capabilities Index",
        label={"GPT-5.2 Pro": (-14, -16, "start"), "GPT-5.5 Pro": (-16, -16, "end"),
               "Claude Fable 5": (0, -20, "middle"), "Claude Fable 5.1": (16, 34, "start"), "GPT-6 Astra": (-16, -16, "end"),
               "Claude Fable 5.2": None},
        note=f"Every model released since 10 Nov 2025; ink = new record on release, line = best model so far. "
             f"Fable 5.2: 174 (90% CI 170&#8211;179), +5 over GPT-6 Astra. Source: {ECI_SRC}")),
    ("fable-preise", partial(
        l_table, cat="Prices · USD per 1M tokens", model="Fable 5.2", head="2&#215; Opus per token, cheaper per task",
        top=420, row_h=48, cam=(0.42, 0.66, -0.08, 300),
        cols=[("MODEL", 340, "left"), ("LAB", 200, "left"), ("INPUT", 150, "right"), ("OUTPUT", 150, "right"),
              ("COST / TASK*", 220, "right")],
        rows=[["Fable 5.2", "Anthropic", "$8.00", "$40.00", "$17.94"], ["Opus 5.5", "Anthropic", "$4.00", "$20.00", "$24.77"],
              ["Sonnet 5.5", "Anthropic", "$2.00", "$10.00", "$16.18"], ["Haiku 5.5", "Anthropic", "$0.10", "$0.50", "$3.18"],
              ["GPT-6 Astra", "OpenAI", "$10.00", "$50.00", "$21.28"], ["GPT-6.1 Sol", "OpenAI", "$2.00", "$10.00", "$3.61"],
              ["GPT-6.1 Terra", "OpenAI", "$1.00", "$5.00", "$2.94"],
              ["DeepSeek V4.1 Flash", "DeepSeek", "$0.30", "$1.20", "$0.66"], ["Muse Ember", "Meta", "$0.10", "$0.50", "$0.15"]],
        strong=("Fable 5.2", "Opus 5.5"),
        note="List prices, standard tier, from the providers&#8217; pages via artificialanalysis.ai, 10 Nov 2026. "
             "*Average cost of one Vals Index task (vals.ai, 9 Nov 2026): fewer tokens can beat a lower price.")),
    ("fable-vals", partial(
        l_pareto, model="Fable 5.2", head="#1 on the GDP-weighted Vals Index, at 72% of Opus&#8217;s cost",
        label={"anthropic/claude-fable-5-2": (24, -14, "start"), "anthropic/claude-opus-5-5": (20, 34, "start"),
               "google/gemini-4-carbon": (-18, -20, "end"), "openai/gpt-6.1-sol": (-16, -18, "end"),
               "deepseek/deepseek-v4.1-flash-1017": (-16, -18, "end"), "meta/muse-ember": (14, 36, "start")},
        note=f"Accuracy on agentic finance, coding, legal and tax tasks, weighted by each sector&#8217;s share of U.S. GDP; "
             f"line = Pareto frontier, bars = &#177;1 standard error. Source: {VALS_SRC}")),
    ("fable-vals-liste", partial(
        l_table, cat="Benchmarks · Vals AI", model="Fable 5.2", head="Same accuracy as Opus 5.5, in half the time",
        cols=[("MODEL", 380, "left"), ("ACCURACY", 200, "right"), ("COST / TASK", 220, "right"),
              ("TOKENS / TASK", 240, "right"), ("TIME / TASK", 220, "right")],
        rows=vals_rows(["anthropic/claude-fable-5-2", "anthropic/claude-sonnet-5-5", "google/gemini-4-carbon",
                        "anthropic/claude-opus-5-5", "google/gemini-4-argon", "meta/muse-wonder-full", "openai/gpt-6-astra"]),
        strong=("Fable 5.2", "Opus 5.5"), top=430, row_h=60,
        note=f"Vals Index leaderboard, top 7. The top four are within one standard error (&#177;1.0 points) of each other. "
             f"Source: {VALS_SRC}")),
    ("fable-community", partial(
        l_tweet_video, cat="Community", model="Fable 5.2", head="4.7&#215; less compute than Opus 5.5",
        name="Dominik Scholz", handle="@dom_scholz", avatar="assets/recap/dom-scholz-avatar.jpg",
        text="Opus 5.5 vs. Fable 5.2<br>waaaay quicker, almost 0-shot from fable<br>Fabulous",
        meta="00:20 · 10 Nov 2026",
        video="assets/recap/dom-scholz-fable-vs-opus.mp4", poster="assets/recap/dom-scholz-fable-vs-opus.jpg")),
    ("fable-zitat", partial(
        l_statement, text="&#8220;For most coding and knowledge tasks, we recommend starting with Opus 5.5, "
                          "our strongest daily driver.&#8221;",
        src="@claudeai, 9 Nov 2026", size=64, top=200, model="Opus 5.5")),
]


LAYOUTS = [("orga", l_orga), ("agenda", l_agenda), ("website", l_website), *MUSE, *FABLE, ("story", l_story), ("tweet", l_tweet), ("tweets", l_tweets),
           ("tweet-media", l_tweet_media), ("drei-spalten", l_drei), ("zahl", l_zahl), ("talk", l_talk),
           ("statement", l_statement), ("frage", l_frage),
           ("diskussion-tempo", partial(
               l_cadence, question="Are the frontier labs pacing themselves?",
               bands=(("2026-09-01", "2026-09-03", "1&#8211;3 Sep: all four labs ship", "end"),
                      ("2026-09-22", "2026-09-30", "22&#8211;30 Sep: again", "start")),
               note="Every model in Epoch&#8217;s list, 10 Nov 2025 &#8211; 10 Nov 2026; filled = new best of that lab. "
                    "Since April, Anthropic has set a new lab best every 2&#8211;7 weeks. Source: epoch.ai/eci")),
           ("diskussion-dominanz", partial(
               l_labs, question="Will OpenAI &amp; Anthropic<br>still dominate in a year?", top=410,
               note="Best Epoch Capabilities Index score per lab. A year ago: Google &#8722;6, Meta &#8722;19. "
                    "Not in Epoch yet: Gemini 4 Carbon, 0.9 points behind Fable 5.2 on the Vals Index. Source: epoch.ai/eci")),
           ("tierlist", l_fullscreen), ("ende", l_ende)]


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
        add(f"{k:02d}-{name}", cam, html + chrome(k, n, ed, with_logo=name != "orga") if name != "tierlist" else html)

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
