#!/usr/bin/env python3
"""Build the WAISS presentation: one self-contained HTML deck with ONE blob that only rotates and
travels between the slides (same shape the whole time, no morphing).

    python3 -X utf8 tools/deck.py editions/001.json     # -> build/deck/index.html (recap) + build/master/index.html
    node tools/export-deck.js                           # -> exports/deck/*.png + waiss-slides.pdf
    node tools/export-deck.js build/master exports/master

The master deck (MASTER) shows every layout once with [placeholders]; the recap (LAYOUTS) has only real slides.

Present: open build/deck/index.html, arrow keys / space / click (left third = back), F = fullscreen,
#N in the URL jumps to slide N. `index.html?print` is the static layout used for the PDF fallback.

Every layout is a function below returning (cam, html): cam = (zoom, shift-x, shift-y, rotation in degrees)
for the blob on that slide; every content slide uses CONTENT_CAM, so the blob sits still bottom right. Slide copy is English.
Categories for the recap (eyebrow above the title; the order is chronological): Releases, News, Drama.
Tweets: l_tweet, l_tweets, l_tweet_media render static cards in the WAISS look (no embed widget); fill name,
handle, text, and optionally avatar= / media= (image path) in tweet_card().
"""
import base64, json, math, re, shutil, sys
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
# Every content slide parks the blob in the same spot, bottom right above the logo, so it stays still while you click
# through; only the framing slides (title, orga, agenda, statement, question, tier list, end) move it.
CONTENT_CAM = (0.24, 0.755, -0.245, 60)
CONTENT_RIGHT = 1600  # content slides keep everything left of this from y=660 down: that corner is the blob's


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
    # "wifi" in the edition: off unless set. false / missing = no WLAN tile, true = placeholder tile,
    # {"ssid", "password"} = tile with a join-the-network QR code.
    w = ed.get("wifi") or False
    wlan = ("" if w is False else qr_tile(None, "WLAN", "[Network]<br>[Password]", size=400) if w is True
            else qr_tile(wifi_payload(w), "WLAN", f'{w["ssid"]}<br>{w["password"]}', size=400))
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
        + (f'<div class="abs" style="left:1400px;top:190px">{wlan}</div>' if wlan else ""))
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
    QR = 300
    tel = data_uri("assets/logo/telos-circle.svg", "image/svg+xml")
    gh = data_uri("assets/logo/github.svg", "image/svg+xml", INK)
    env = (f'<svg viewBox="0 0 24 24" width="44" height="44" fill="none" stroke="{INK}" stroke-width="2" '
           f'stroke-linejoin="round"><rect x="2.5" y="5" width="19" height="14" rx="2.5"/><path d="M3 6.5l9 6.5 9-6.5"/></svg>')
    a = f'color:{INK};text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:8px'
    row = lambda icon, html: (f'<div style="display:flex;align-items:center;gap:26px;font-size:40px;font-weight:600;'
                              f'margin-top:34px">{icon}<span>{html}</span></div>')
    qr = f'<div class="qr" style="--s:{QR}px"><div class="tile">{qr_art(url, tel)}</div></div>'
    html = (f'<div class="abs" style="left:132px;top:{HEAD_TOP}px;display:flex;align-items:center;gap:64px">{qr}'
            f'<div>{eyebrow("Slides &amp; website")}'
            f'<h2 style="font-size:{TITLE_PX}px;margin-top:16px"><a href="{url}" style="{a};text-decoration-thickness:4px">'
            f'{short(url)}</a></h2>'
            f'<div style="font-size:34px;color:{MUTED};margin-top:22px">Tonight&#8217;s slides, past and upcoming editions.</div></div></div>'
            f'<div class="abs" style="left:120px;right:120px;top:{HEAD_TOP + QR + 60}px;border-top:2px solid {INK}"></div>'
            f'<div class="abs" style="left:120px;top:{HEAD_TOP + QR + 100}px;width:1300px">'
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
    return CONTENT_CAM, html


def l_tweet(ed, cat="Drama", model=None, **card_kw):
    kw = dict(name="[Name]", handle="[@handle]", text="[The tweet, in full. Short enough to read from the back row.]",
              width=1060, size=50)
    card = tweet_card(**{**kw, **card_kw})
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px">{eyebrow(cat)}{model_h(model) if model else ""}</div>'
            f'<div class="abs" style="left:130px;top:{340 if model else 230}px">{card}</div>')
    return CONTENT_CAM, html


def l_tweets(ed):
    a = tweet_card("[Name]", "[@handle]", "[First tweet]", width=700, size=40)
    b = tweet_card("[Name]", "[@reply]", "[The reply, or the other side of it]", width=700, size=40)
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px">{eyebrow("Drama")}</div>'
            f'<div class="abs" style="left:130px;top:230px">{a}</div>'
            f'<div class="abs" style="left:{CONTENT_RIGHT - 700}px;top:290px">{b}</div>')
    return CONTENT_CAM, html


def l_tweet_media(ed, cat="News", model=None, **card_kw):
    kw = dict(name="[Name]", handle="[@handle]", text="[Tweet text with a screenshot or chart attached.]",
              width=900, size=40, media_h=300)
    card = tweet_card(**{**kw, **card_kw})
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px">{eyebrow(cat)}{model_h(model) if model else ""}</div>'
            f'<div class="abs" style="left:130px;top:{340 if model else 230}px">{card}</div>')
    return CONTENT_CAM, html


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
            f'<div class="abs" style="left:120px;right:{1920 - CONTENT_RIGHT}px;top:{430 if model else 340}px;display:grid;'
            f'grid-template-columns:repeat(3,minmax(0,1fr));gap:56px">{cards}</div>')
    return CONTENT_CAM, html


def l_zahl(ed, cat="Number of the month", num="[73 %]", text="[What the number means, in one sentence]", src="[link]",
           model=None):
    html = (f'<div class="abs" style="left:100px;top:{HEAD_TOP}px">{eyebrow(cat, "margin-left:20px")}'
            + (model_h(model, extra="margin-left:20px") if model else "")
            + f'<h2 style="font-size:{140 if model else 360}px;line-height:1;margin:{"36px 0 0 20px" if model else "10px 0 0"}">{num}</h2>'
            f'<div style="font-size:44px;margin:10px 0 0 20px;width:{1000 if model else 900}px;line-height:1.25">{text}</div>'
            f'<div class="mono" style="font-size:20px;margin:28px 0 0 20px">Source: {src}</div></div>')
    return CONTENT_CAM, html


def l_text(ed, cat="Takeaways", head="[Title]", model=None, items=(), text="", note="", size=44):
    """Text only: a short list (items) or a paragraph (text) under eyebrow + title, e.g. takeaways or the term of the month.
    items: strings, or (lead, rest) pairs whose lead is set bold; they are numbered 01, 02, ... text: one paragraph,
    <br><br> for a second one. With model= the name (or the term) is the biggest thing on the slide, head its subline."""
    title = (model_h(model) + subline(head)) if model else f'<h2 style="font-size:{TITLE_PX}px;margin-top:16px">{head}</h2>'
    if items:
        body = "".join(
            f'<div style="display:flex;gap:40px;align-items:baseline;border-top:2px solid {INK};padding:24px 0 26px">'
            f'<span class="mono" style="font-size:24px;width:56px;flex:none">{k:02d}</span>'
            f'<span style="font-size:{size}px;line-height:1.25;font-weight:500">'
            + (f'<strong style="font-weight:700">{it[0]}</strong> {it[1]}' if isinstance(it, tuple) else it)
            + '</span></div>' for k, it in enumerate(items, 1))
    else:
        body = f'<div style="font-size:{size}px;line-height:1.35;font-weight:500">{text}</div>'
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:1300px">{eyebrow(cat)}{title}</div>'
            f'<div class="abs" style="left:120px;top:{430 if model else 340}px;width:1340px">{body}</div>'
            f'<div class="abs mono" style="left:120px;bottom:{CORNER + 4}px;width:1380px;font-size:19px;line-height:1.3;'
            f'letter-spacing:.04em">{note}</div>')
    return CONTENT_CAM, html


def l_talk(ed):
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:900px">{eyebrow("Show &amp; Tell")}'
            f'<h2 style="font-size:{TITLE_PX}px;margin:16px 0 48px">[Talk title]</h2>'
            f'<div style="font-size:40px;font-weight:600">[Name]</div>'
            f'<div style="font-size:32px;color:{MUTED};margin-top:8px">[Role · @handle]</div></div>'
            f'<div class="abs" style="left:1100px;top:{HEAD_TOP}px;width:700px;height:440px;border:2px solid {INK};'
            f'background:rgba(255,255,255,.55);display:flex;align-items:center;justify-content:center">'
            f'<span class="mono" style="font-size:24px">[Screenshot / demo]</span></div>')
    return CONTENT_CAM, html


def l_statement(ed, text="[One sentence that sticks.]", src="[Source]", size=150, top=340, model=None):
    html = (f'<div class="abs" style="left:160px;right:160px;top:{top}px;text-align:center">'
            + (model_h(model, extra="margin:0 0 56px") if model else "")
            + f'<h2 style="font-size:{size}px;line-height:{1.1 if model else .98};font-weight:{600 if model else 800}">{text}</h2>'
            f'<div class="mono" style="font-size:24px;margin-top:48px;color:{INK}">— {src}</div></div>')
    return (2.3, 0.0, -0.02, 150), html


def l_frage(ed, q="What surprised you this month?", cat="Open round", size=100):
    html = (f'<div class="abs" style="left:160px;right:160px;top:200px;text-align:center">{eyebrow(cat)}'
            f'<h2 style="font-size:{size}px;line-height:1.02;margin-top:36px">{q}</h2></div>')
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
            cam=CONTENT_CAM):
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
            f'<div class="abs" style="left:120px;right:{1920 - CONTENT_RIGHT}px;top:{top}px;display:grid;'
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
    return CONTENT_CAM, html


MEDIA = []  # files the slides load on demand: copied to <deck>/media/ by main()


def l_tweet_video(ed, cat="Community", model=None, head="", video=None, poster=None, ratio=2.0, **card_kw):
    """Model name + subline + a small tweet card on the left, the tweet's video large on the right.
    The video is a file next to the deck (media/, see MEDIA), not part of the HTML: it is fetched only when someone
    clicks it, then plays muted and looped; a click pauses it again, leaving the slide rewinds it. Its poster (embedded)
    stands in until then and in the PNG / PDF export."""
    kw = dict(name="[Name]", handle="[@handle]", text="[Tweet text]", width=580, size=28)
    card = tweet_card(**{**kw, **card_kw})
    vw = 860
    if video:
        MEDIA.append(video)
        vid = (f'<div class="vid" style="width:{vw}px;height:{vw / ratio:.0f}px">'
               f'<video class="clip" data-src="media/{Path(video).name}" poster="{data_uri(poster, "image/jpeg")}" '
               f'muted loop playsinline preload="none" tabindex="-1"></video>'
               f'<div class="play" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></div></div>')
    else:  # master deck: a placeholder box
        vid = (f'<div style="width:{vw}px;height:{vw / ratio:.0f}px;border:2px solid {INK};border-radius:18px;'
               f'background:rgba(255,255,255,.55);display:flex;align-items:center;justify-content:center">'
               f'<span class="mono" style="font-size:24px">[Video]</span></div>')
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:600px">{eyebrow(cat)}{model_h(model) if model else ""}'
            f'{subline(head)}</div>'
            f'<div class="abs" style="left:130px;top:420px">{card}</div>'
            f'<div class="abs" style="left:{CONTENT_RIGHT - vw}px;top:380px">{vid}</div>')
    return CONTENT_CAM, html


def l_table(ed, cat="Benchmarks", model=None, head="", cols=(), rows=(), strong=(), note="", top=430, row_h=56,
            cam=CONTENT_CAM):
    """A plain table for numbers people compare across a row. cols: [(label, width px, align)], rows: [[cell, ...]].
    Rows whose first cell is in `strong` are drawn in ink and bold, the rest muted; a row starting with None is a
    divider labelled by its second cell. A table wider than the room left of the blob gets its widest column narrowed
    (its text wraps instead)."""
    over = sum(w for _, w, _ in cols) + 28 * (len(cols) - 1) - (CONTENT_RIGHT - 120)
    if over > 0:
        k = max(range(len(cols)), key=lambda i: cols[i][1])
        cols = [(c, w - over, a) if i == k else (c, w, a) for i, (c, w, a) in enumerate(cols)]
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
    W, H, L, T, Rr, B = CONTENT_RIGHT - 30, 470, 70, 20, 40, 50  # placed at x=70: the plot ends at CONTENT_RIGHT
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
    return CONTENT_CAM, html


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
    W, H, L, Rr, B, row = CONTENT_RIGHT - 120, 560, 170, 250, 50, 118  # the counts on the right end at CONTENT_RIGHT
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
    return CONTENT_CAM, _chart_frame(W, H, svg, question, note)


def l_labs(ed, question="", since="2025-11-10", until="2026-11-10", note="", ymin=130, ymax=178, top=330,
           labs=(("Anthropic", 5, None), ("OpenAI", 5, "12 7"), ("Google", 3, None), ("Meta", 3, "12 7"))):
    """Each lab's best Epoch Capabilities Index score so far, as a step line per lab; labelled at the right end with
    the gap to the leader. labs: (name, stroke width, dash) - ink for the first two, muted for the rest."""
    from datetime import date
    rows = eci_rows()
    W, H, L, T, Rr, B = CONTENT_RIGHT - 120, 560 - (top - 330), 70, 10, 330, 50  # end labels stop at CONTENT_RIGHT
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
    return CONTENT_CAM, _chart_frame(W, H, svg, question, note, top=top)


def l_timeline(ed, cat="Releases", head="", model=None, lanes=(), since="2026-10-01", until="2026-11-12",
               ticks=(), today=None, note="", row=92, top=300, cam=CONTENT_CAM):
    """Swimlane timeline: one row per lab, one marker per release, labelled directly.
    lanes: [(lab, [(date, label, kind), ...])], kind: "pub" (ink dot, everyone can use it), "open" (ink diamond, open
    weights), "gated" (hollow, selected customers only), "teaser" (dashed hollow, announced only).
    Labels go above the marker, or below when they would collide with the previous label above."""
    from datetime import date
    W, L, Rr, T, B = CONTENT_RIGHT - 120, 190, 40, 30, 50
    H = T + row * len(lanes) + B
    d0, d1 = date.fromisoformat(since), date.fromisoformat(until)
    X = lambda d: L + (date.fromisoformat(d) - d0).days / (d1 - d0).days * (W - L - Rr)
    width = lambda s: len(re.sub(r"&#?\w+;", "x", s)) * 11.5
    out = ""
    for d, lab in ticks:
        out += (f'<line x1="{X(d):.1f}" x2="{X(d):.1f}" y1="{T - 10}" y2="{H - B}" stroke="#E4E0D7" stroke-width="1"/>'
                f'<text x="{X(d):.1f}" y="{H - 12}" text-anchor="middle" class="ax">{lab}</text>')
    if today:
        out += (f'<line x1="{X(today):.1f}" x2="{X(today):.1f}" y1="{T - 20}" y2="{H - B}" stroke="{INK}" stroke-width="2" '
                f'stroke-dasharray="6 6"/><text x="{X(today):.1f}" y="{T - 28}" text-anchor="middle" class="ax">TODAY</text>')
    for k, (lab, evs) in enumerate(lanes):
        y = T + row * k + row / 2
        out += (f'<line x1="{L}" x2="{W - Rr}" y1="{y:.1f}" y2="{y:.1f}" stroke="#D9D5CC" stroke-width="1"/>'
                f'<text x="0" y="{y + 10:.1f}" class="lb">{lab}</text>')
        last = {"up": [], "down": []}
        for d, text, kind in sorted(evs):
            x, w = X(d), width(text)
            edge = X(today) - 6 if today else W - Rr  # a label never crosses the TODAY line or the plot edge
            anchor, x0 = ("end", x - 14 - w) if x + w / 2 > edge else ("middle", x - w / 2)
            free = lambda sd: all(x0 > b + 16 or x0 + w < a - 16 for a, b in last[sd])
            side = "up" if free("up") else "down"
            last[side].append((x0, x0 + w))
            ty = y - 22 if side == "up" else y + 40
            on = kind in ("pub", "open")
            if kind == "open":
                out += (f'<rect x="{x - 9:.1f}" y="{y - 9:.1f}" width="18" height="18" fill="{INK}" stroke="#F5F3EE" '
                        f'stroke-width="3" transform="rotate(45 {x:.1f} {y:.1f})"/>')
            else:
                out += (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{10 if on else 8}" '
                        + (f'fill="{INK}" stroke="#F5F3EE" stroke-width="3"/>' if on else
                           f'fill="#F5F3EE" stroke="{MUTED}" stroke-width="3"' + (' stroke-dasharray="4 4"' if kind == "teaser" else "") + '/>'))
            out += f'<text x="{x - 14 if anchor == "end" else x:.1f}" y="{ty:.1f}" text-anchor="{anchor}" class="ev{"" if on else " m"}">{text}</text>'
    svg = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" style="overflow:visible;display:block">'
           f'<style>.ax{{font:400 19px "IBM Plex Mono",monospace;fill:{MUTED};letter-spacing:.04em}}'
           f'.lb{{font:700 30px Archivo,sans-serif;fill:{INK}}}.ev{{font:600 22px Archivo,sans-serif;fill:{INK}}}'
           f'.ev.m{{font-weight:500;fill:{MUTED}}}</style>{out}'
           f'<line x1="{L}" x2="{W - Rr}" y1="{H - B}" y2="{H - B}" stroke="{INK}" stroke-width="2"/></svg>')
    title = (model_h(model) + subline(head)) if model else f'<h2 style="font-size:{TITLE_PX}px;margin-top:16px">{head}</h2>'
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:1300px">{eyebrow(cat)}{title}</div>'
            f'<div class="abs" style="left:120px;top:{top}px">{svg}</div>'
            f'<div class="abs mono" style="left:120px;bottom:{CORNER + 4}px;width:1380px;font-size:19px;line-height:1.3;'
            f'letter-spacing:.04em">{note}</div>')
    return cam, html


def l_ranges(ed, cat="", model=None, head="", ymin=0.8, ymax=2.2, yticks=(), fmt="${:.1f}T", points=(), events=(),
             note="", top=430, H=470):
    """A number over time as ranges, one column per data point (dates are labels, not a linear axis, so a busy week
    still gets room). points = [(date label, low, high, value label, source, kind)], kind "filed"/"round" (ink) or
    "talk" (muted, reported investor talk): a bar from low to high, a dot when low == high, a thin line joins the
    midpoints, value + source above. events = [(position between columns, e.g. 4.5, label, row)]: dashed lines."""
    W, L, Rr, T, B = CONTENT_RIGHT - 120, 90, 10, 80, 50
    n = len(points)
    X = lambda i: L + (i + .5) * (W - L - Rr) / n
    Y = lambda v: T + (ymax - v) / (ymax - ymin) * (H - T - B)
    out = "".join(f'<line x1="{L}" x2="{W - Rr}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#D9D5CC" stroke-width="1"/>'
                  f'<text x="{L - 14}" y="{Y(v) + 7:.1f}" text-anchor="end" class="ax">{fmt.format(v)}</text>' for v in yticks)
    for pos, lab, row in events:
        out += (f'<line x1="{X(pos):.1f}" x2="{X(pos):.1f}" y1="{T - 30 - 26 * row}" y2="{H - B}" stroke="{MUTED}" '
                f'stroke-width="1.5" stroke-dasharray="5 6"/><text x="{X(pos) + 8:.1f}" y="{T - 36 - 26 * row}" class="ev">{lab}</text>')
    out += (f'<polyline points="{" ".join(f"{X(i):.1f},{Y((p[1] + p[2]) / 2):.1f}" for i, p in enumerate(points))}" '
            f'fill="none" stroke="#C9C5BB" stroke-width="2"/>')
    for i, (d, lo, hi, val, src, kind) in enumerate(points):
        x, on = X(i), kind in ("filed", "round")
        col = INK if on else MUTED
        if hi > lo:
            out += (f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{Y(hi):.1f}" y2="{Y(lo):.1f}" stroke="{col}" stroke-width="12" '
                    f'stroke-linecap="round"/>')
        else:
            out += (f'<circle cx="{x:.1f}" cy="{Y(lo):.1f}" r="10" '
                    + (f'fill="#F5F3EE" stroke="{INK}" stroke-width="4"/>' if kind == "round" else f'fill="{col}"/>'))
        out += (f'<text x="{x:.1f}" y="{Y(hi) - 46:.1f}" text-anchor="middle" class="lb{"" if on else " m"}">{val}</text>'
                f'<text x="{x:.1f}" y="{Y(hi) - 22:.1f}" text-anchor="middle" class="ev">{src}</text>'
                f'<text x="{x:.1f}" y="{H - 14}" text-anchor="middle" class="ax">{d}</text>'
                f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{H - B}" y2="{H - B + 8}" stroke="{INK}" stroke-width="2"/>')
    svg = (f'<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" style="overflow:visible;display:block">'
           f'<style>.ax{{font:400 19px "IBM Plex Mono",monospace;fill:{MUTED};letter-spacing:.04em}}'
           f'.lb{{font:700 28px Archivo,sans-serif;fill:{INK}}}.lb.m{{font-weight:500;fill:{MUTED}}}'
           f'.ev{{font:500 18px "IBM Plex Mono",monospace;fill:{MUTED};letter-spacing:.02em}}</style>{out}'
           f'<line x1="{L}" x2="{L}" y1="{T - 10}" y2="{H - B}" stroke="{INK}" stroke-width="2"/>'
           f'<line x1="{L}" x2="{W - Rr}" y1="{H - B}" y2="{H - B}" stroke="{INK}" stroke-width="2"/></svg>')
    title = (model_h(model) + subline(head)) if model else f'<h2 style="font-size:{TITLE_PX}px;margin-top:16px">{head}</h2>'
    html = (f'<div class="abs" style="left:120px;top:{HEAD_TOP}px;width:1300px">{eyebrow(cat)}{title}</div>'
            f'<div class="abs" style="left:120px;top:{top}px">{svg}</div>'
            f'<div class="abs mono" style="left:120px;bottom:{CORNER + 4}px;width:1380px;font-size:19px;line-height:1.3;'
            f'letter-spacing:.04em">{note}</div>')
    return CONTENT_CAM, html


# ------------------------------------------------------------------ show & tell: a looser frame for people's own content
# A show & tell slide is a header (the talk's category, big, top left; speaker top right of it) over one rounded
# "stage" that holds whatever the speaker brings: a logo, screenshots, code, a tweet, a demo. The stage is light
# (TILE_BG) or ink; the blob sits small on its top-right corner, half hidden behind it, and stays there for the whole
# talk. st_frame() is the frame alone (body = any HTML, laid out in a 1760 x 770 box); the st_* layouts below are
# common fillings of it.
ST_X, ST_TOP, ST_BOTTOM = 80, 230, 80
ST_W, ST_H = 1920 - 2 * ST_X, 1080 - ST_TOP - ST_BOTTOM  # 1760 x 770
ST_CAM = (0.19, 0.745, 0.3, 40)  # blob perched on the stage's top-right corner
CREAM = "#F5F3EE"


def st_frame(cat, body, tone="light", pad=72, speaker="Peter Wimberger", center=False):
    dark = tone == "ink"
    bg, fg = (INK, CREAM) if dark else (TILE_BG, INK)
    lay = "display:flex;align-items:center;justify-content:center;" if center else ""
    html = (f'<div class="abs" style="left:{ST_X}px;top:58px"><div class="mono" style="font-size:22px">Show &amp; Tell'
            f'{" &#183; " + speaker if speaker else ""}</div>'
            f'<h2 style="font-size:96px;margin-top:14px;white-space:nowrap">{cat}</h2></div>'
            f'<div class="abs stage" style="left:{ST_X}px;top:{ST_TOP}px;width:{ST_W}px;height:{ST_H}px;'
            f'padding:{pad}px;background:{bg};color:{fg};{lay}">{body}</div>')
    return ST_CAM, html


def st_ph(label, w="100%", h="100%", dark=False, extra=""):
    """Dashed placeholder box for an image / screenshot that is not there yet."""
    c = "rgba(245,243,238,.5)" if dark else MUTED
    return (f'<div style="width:{w};height:{h};border:2px dashed {c};border-radius:24px;display:flex;align-items:center;'
            f'justify-content:center;{extra}"><span class="mono" style="font-size:22px;color:{c}">{label}</span></div>')


def st_img(src, w="100%", h="100%", fit="contain", extra=""):
    if not src:
        return st_ph("[Image]", w, h, extra=extra)
    ext = src.rsplit(".", 1)[-1]
    mime = {"jpg": "image/jpeg", "svg": "image/svg+xml"}.get(ext, f"image/{ext}")
    return f'<img src="{data_uri(src, mime)}" alt="" style="width:{w};height:{h};object-fit:{fit};{extra}">'


def st_cover(ed, cat="[Category]", logo=None, name="[Tool]", tag="[One line: what it is]", url=""):
    """Talk opener: the tool's logo, its name right of it, one line under the name."""
    body = (f'<div style="display:flex;align-items:center;gap:72px">'
            f'<div style="width:300px;height:300px;flex:none">{st_img(logo) if logo else st_ph("[Logo]")}</div>'
            f'<div><h2 style="font-size:190px;line-height:.9">{name}</h2>'
            f'<div style="font-size:42px;font-weight:500;color:{MUTED};margin-top:30px">{tag}</div>'
            + (f'<div class="mono" style="font-size:24px;color:{INK};margin-top:26px">{url}</div>' if url else "")
            + '</div></div>')
    return st_frame(cat, body, center=True)


_HAND = (f'<svg viewBox="0 0 24 24" width="120" height="120" fill="none" stroke="{INK}" stroke-width="1.4" '
         f'stroke-linecap="round" stroke-linejoin="round" style="flex:none"><path d="M18 11V6a2 2 0 0 0-4 0v5"/>'
         f'<path d="M14 10V4a2 2 0 0 0-4 0v6"/><path d="M10 10.5V6a2 2 0 0 0-4 0v8"/>'
         f'<path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/></svg>')


def st_poll(ed, cat="[Category]", qs=("[Who uses it?]", "[Who has heard of it?]")):
    """Show of hands: one big question per row, a hand in front."""
    rows = "".join(f'<div style="display:flex;align-items:center;gap:56px;padding:48px 0;'
                   f'{"border-top:2px solid " + INK if k else ""}">{_HAND}'
                   f'<h2 style="font-size:110px">{q}</h2></div>' for k, q in enumerate(qs))
    return st_frame(cat, f'<div style="width:100%">{rows}</div>', pad=96, center=True)


def st_what(ed, cat="[Category]", term="[What it is, in a few words]", lead="[One sentence that explains it]",
            facts=(("[Key]", "[Value]"),) * 4, picks=(("[Feature]", "[Why it matters to me]"),) * 3,
            picks_label="Why I use it"):
    """What the thing is: term + one sentence, a few hard facts (left), and the speaker's own picks (right, ink cards)."""
    fx = "".join(f'<div style="display:flex;gap:28px;border-top:1px solid {MUTED};padding:16px 0">'
                 f'<span class="mono" style="font-size:20px;width:190px;flex:none;padding-top:6px">{k}</span>'
                 f'<span style="font-size:30px;font-weight:500;line-height:1.25">{v}</span></div>' for k, v in facts)
    pk = "".join(f'<div style="background:{INK};color:{CREAM};border-radius:26px;padding:28px 36px;display:flex;gap:28px;'
                 f'align-items:baseline"><span class="mono" style="font-size:22px;color:#B9B5AB">{k:02d}</span>'
                 f'<div><div style="font-size:40px;font-weight:700;line-height:1.1">{t}</div>'
                 f'<div style="font-size:27px;line-height:1.3;margin-top:8px;color:#D9D5CC">{w}</div></div></div>'
                 for k, (t, w) in enumerate(picks, 1))
    body = (f'<div style="display:grid;grid-template-columns:minmax(0,1fr) 700px;gap:72px;width:100%;height:100%">'
            f'<div><h2 style="font-size:76px;line-height:1">{term}</h2>'
            f'<div style="font-size:34px;line-height:1.3;margin:24px 0 36px;color:{MUTED}">{lead}</div>{fx}</div>'
            f'<div style="display:flex;flex-direction:column;gap:22px">'
            f'<div class="eyebrow" style="font-size:22px">{picks_label}</div>{pk}</div></div>')
    return st_frame(cat, body)


def st_person(ed, cat="[Category]", name="[Name]", photo=None, role="[@handle]", facts=("[Fact]",) * 4, tweet=None):
    """Who's behind it: photo, name, a few facts; one tweet card on the right (tweet=False: none)."""
    av = (f'<div style="width:200px;height:200px;flex:none;border-radius:50%;overflow:hidden;outline:2px solid {INK};'
          f'outline-offset:8px">'
          + (st_img(photo, fit="cover", extra="filter:grayscale(1)") if photo else st_ph("[Photo]", extra="border-radius:50%"))
          + '</div>')
    fx = "".join(f'<div style="display:flex;gap:22px;align-items:baseline;border-top:1px solid {MUTED};padding:16px 0">'
                 f'<span class="mono" style="font-size:20px">{k:02d}</span><span style="font-size:32px;font-weight:500;'
                 f'line-height:1.25">{f}</span></div>' for k, f in enumerate(facts, 1))
    tw = ("" if tweet is False else
          tweet_card(**{**dict(name=name, handle=role, text="[The tweet]", width=720, size=38), **(tweet or {})}))
    body = (f'<div style="display:flex;gap:80px;width:100%;height:100%;align-items:center">'
            f'<div style="flex:1;min-width:0"><div style="display:flex;gap:44px;align-items:center;margin-bottom:34px">{av}'
            f'<div><h2 style="font-size:84px;white-space:nowrap">{name}</h2><div class="mono" style="font-size:24px;margin-top:14px">{role}</div>'
            f'</div></div>{fx}</div>{tw}</div>')
    return st_frame(cat, body)


def st_shots(ed, cat="[Category]", shots=(("", "[Caption]"),), tone="ink"):
    """1-3 screenshots side by side on the stage, each with a short caption below."""
    dark = tone == "ink"
    cap_c = "#B9B5AB" if dark else MUTED
    cells = "".join(f'<figure style="margin:0;display:flex;flex-direction:column;gap:20px;min-width:0;height:100%">'
                    f'<div style="flex:1;min-height:0;display:flex;align-items:center;justify-content:center">'
                    + (st_img(src, extra="border-radius:14px") if src else st_ph("[Screenshot]", dark=dark))
                    + f'</div><figcaption class="mono" style="font-size:22px;color:{cap_c};text-align:center">{cap}'
                      f'</figcaption></figure>' for src, cap in shots)
    body = (f'<div style="display:grid;grid-template-columns:repeat({len(shots)},minmax(0,1fr));gap:48px;'
            f'width:100%;height:100%">{cells}</div>')
    return st_frame(cat, body, tone=tone, pad=56)


def st_demo(ed, cat="[Category]", text="Live demo", sub="[What you are about to see]"):
    body = (f'<div style="text-align:center"><div class="mono" style="font-size:28px;color:#B9B5AB;display:flex;'
            f'align-items:center;justify-content:center;gap:18px"><span class="rec"></span>Live</div>'
            f'<h2 style="font-size:220px;margin-top:30px">{text}</h2>'
            f'<div style="font-size:40px;color:#D9D5CC;margin-top:34px">{sub}</div></div>')
    return st_frame(cat, body, tone="ink", center=True)


def st_split(ed, cat="[Category]", title="[Concept]", sub="[One line]", left="", right="",
             left_label="[Before]", right_label="[After]"):
    """Concept slide: title + line on top, two panes below (code | diagram, before | after, problem | fix)."""
    pane = lambda lab, inner, dark: (
        f'<div style="display:flex;flex-direction:column;gap:16px;min-width:0;height:100%">'
        f'<div class="eyebrow" style="font-size:22px">{lab}</div>'
        f'<div style="flex:1;min-height:0;border-radius:26px;padding:36px 40px;'
        f'{"background:" + INK + ";color:" + CREAM if dark else "border:2px solid " + INK};overflow:hidden">'
        f'{inner or st_ph("[Code / diagram]", dark=dark)}</div></div>')
    body = (f'<div style="display:flex;flex-direction:column;width:100%;height:100%">'
            f'<h2 style="font-size:76px">{title}</h2><div style="font-size:34px;color:{MUTED};margin:16px 0 36px">{sub}</div>'
            f'<div style="flex:1;min-height:0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:48px">'
            f'{pane(left_label, left, True)}{pane(right_label, right, False)}</div></div>')
    return st_frame(cat, body, pad=64)


def sticker(fn, img, left, top, width, rot=-8):
    """Wrap a layout: put an image on top of it like a sticker (slight tilt, soft shadow, crisp pixels)."""
    def wrapped(ed, **kw):
        cam, html = fn(ed, **kw)
        src = data_uri(img, "image/" + img.rsplit(".", 1)[-1].replace("jpg", "jpeg"))
        return cam, html + (f'<img class="abs" src="{src}" alt="" style="left:{left}px;top:{top}px;width:{width}px;'
                            f'transform:rotate({rot}deg);image-rendering:pixelated;'
                            f'filter:drop-shadow(0 10px 14px rgba(0,0,0,.22))">')
    return wrapped


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
        panels=[("Intelligence Index", "Artificial Analysis v5, max effort",
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
        lab_w=300, width=1150, top=430,
        panels=[(None, None,
                 [("Claude Fable 5.2", 64.6), ("Gemini 4 Carbon", 60.0), ("Claude Opus 5.5", 59.1), ("GPT-6 Astra", 56.9),
                  ("GPT-6.1 Sol", 54.6), ("Claude Sonnet 5.5", 54.5), ("GPT-6.1 Terra", 51.3), ("Gemini 4 Argon", 50.4),
                  ("Muse Wonder Full", 50.1), ("Claude Fable 5.1", 49.2)],
                 {"max": 70, "fmt": "{:.0f}", "row": 46, "bar": 28})],
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
        top=420, row_h=48,
        cols=[("MODEL", 340, "left"), ("LAB", 200, "left"), ("INPUT", 150, "right"), ("OUTPUT", 150, "right"),
              ("COST / TASK*", 220, "right")],
        rows=[["Fable 5.2", "Anthropic", "$8.00", "$40.00", "$17.94"], ["Opus 5.5", "Anthropic", "$4.00", "$20.00", "$24.77"],
              ["Sonnet 5.5", "Anthropic", "$2.00", "$10.00", "$16.18"], ["Haiku 5.5", "Anthropic", "$0.10", "$0.50", "$3.17"],
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
        note=f"Vals Index leaderboard, top 7. The top four are within 1.2 points, their &#177;1 SE error bars overlap. "
             f"Source: {VALS_SRC}")),
    ("fable-community", partial(
        l_tweet_video, cat="Community", model="Fable 5.2", head="4.7&#215; less compute than Opus 5.5",
        name="Dominik Scholz", handle="@dom_scholz", avatar="assets/recap/dom-scholz-avatar.jpg",
        text="Opus 5.5 vs. Fable 5.2<br>waaaay quicker, almost 0-shot from fable<br>Fabulous",
        meta="00:20 · 10 Nov 2026",
        video="assets/recap/dom-scholz-fable-vs-opus.mp4", poster="assets/recap/dom-scholz-fable-vs-opus.jpg")),
    ("fable-zitat", partial(
        l_statement, text="&#8220;For most coding and knowledge tasks, we recommend that users start with Claude Opus 5.5, "
                          "our strongest daily driver [&#8230;]&#8221;",
        src="Anthropic, Fable 5.2 announcement, 9 Nov 2026", size=64, top=200, model="Opus 5.5")),
]


# ----------------------------------------------------------------- recap: the month's releases at a glance
RELEASES = [
    ("releases", partial(
        l_timeline, cat="Releases · 1 Oct &#8211; 10 Nov 2026", head="Eight labs, six weeks",
        today="2026-11-10",
        ticks=(("2026-10-01", "1 OCT"), ("2026-10-08", "8 OCT"), ("2026-10-15", "15 OCT"), ("2026-10-22", "22 OCT"),
               ("2026-10-29", "29 OCT"), ("2026-11-05", "5 NOV")),
        lanes=(("Anthropic", (("2026-10-07", "Haiku 5.5", "pub"), ("2026-11-09", "Fable 5.2", "pub"),
                              ("2026-11-09", "Mythos 5.2", "gated"))),
               ("OpenAI", (("2026-10-26", "GPT-6.1 Terra", "pub"), ("2026-10-30", "GPT-6 Rosalind", "gated"),
                           ("2026-11-05", "ChatGPT Images 2.6", "pub"), ("2026-11-05", "GPT-6 Cyber", "gated"))),
               ("Google", (("2026-10-13", "Gemini 4 Argon", "pub"), ("2026-10-27", "Genie 4", "gated"),
                           ("2026-10-28", "Gemini 4 Carbon", "gated"))),
               ("Meta", (("2026-10-12", "Muse Wonder", "pub"), ("2026-10-15", "Muse Spark Open", "open"), ("2026-11-09", "Muse Ember", "pub"))),
               ("Mistral", (("2026-10-06", "Large 4 preview", "pub"), ("2026-10-29", "Mistral Large 4", "open"))),
               ("China", (("2026-10-17", "DeepSeek Flash 1017", "open"), ("2026-10-23", "Kimi K3.1 Pro", "pub"), ("2026-11-04", "K3.1 weights", "open"),
                          ("2026-11-06", "Qwen teaser", "teaser")))),
        note="Ink dot = available to everyone &#183; diamond = open weights &#183; hollow = selected customers only "
             "(cyber and life-science programs, trusted testers) &#183; dashed = announced only. Argon: date of general availability.")),
]


# ----------------------------------------------------------------- recap: the rest of the month, in agenda order
AA5 = "artificialanalysis.ai, Intelligence Index v5.0.1, 10 Nov 2026"
GOOGLE = [
    ("argon-tweet", partial(
        l_tweet, cat="Releases · Google · GA 13 Oct", model="Gemini 4 Argon", size=56, width=1150,
        name="Fran&#231;ois Chollet", handle="@fchollet", avatar="assets/recap/fchollet-avatar.jpg",
        text="Argon has a similar performance profile on ARC-AGI-3 as Astra. Google is back at the frontier.",
        meta="18:51 · 15 Oct 2026")),
    ("carbon-tweet", partial(
        l_tweet, cat="Releases · Google · 28 Oct", model="Gemini 4 Carbon", size=34, width=1300,
        name="Sundar Pichai", handle="@sundarpichai", avatar="assets/recap/sundarpichai-avatar.jpg",
        text="I did say we&#8217;d be releasing our models periodically...introducing Gemini 4 Carbon, our next frontier model."
             "<br><br>Following Argon&#8217;s release just two weeks ago, Carbon shows the pace at which we&#8217;re pushing the "
             "frontier, it ranks #1 on the recently updated v5.0 of @ArtificialAnlys Intelligence Index at 59. [&#8230;]"
             "<br><br>Some trusted cyber defenders will get access starting this week.",
        meta="18:01 · 28 Oct 2026")),
    ("google-aa", partial(
        l_bench, cat="Benchmarks · Artificial Analysis", model="Gemini 4 Carbon", head="Google is back: #2, behind Fable 5.2",
        lab_w=300, width=1150, top=430, hi=1,
        panels=[(None, None,
                 [("Claude Fable 5.2", 65), ("Gemini 4 Carbon", 60), ("Claude Opus 5.5", 59), ("GPT-6 Astra", 57),
                  ("GPT-6.1 Sol", 55), ("Claude Sonnet 5.5", 55), ("GPT-6.1 Terra", 51), ("Gemini 4 Argon", 50),
                  ("Muse Wonder Full", 50)],
                 {"max": 70, "fmt": "{:.0f}", "row": 48, "bar": 30})],
        note=f"Highest effort per model. Carbon was #1 from 28 Oct until Fable 5.2 on 9 Nov, and still has no public API. "
             f"Argon: $2 / $10 until 30 Nov, then $4 / $20, up to 1M output tokens. Source: {AA5}")),
]

CHINA = [
    ("kimi-tweet", partial(
        l_tweet, cat="Releases · Moonshot · 23 Oct, weights 4 Nov", model="Kimi K3.1 Pro", size=50, width=1150,
        name="Kimi.ai", handle="@Kimi_Moonshot", avatar="assets/recap/kimi-avatar.jpg",
        text="Releasing the model weights of Kimi K3.1 Pro: huggingface.co/moonshotai/Kimi-K3.1-Pro<br>"
             "We&#8217;ll keep advancing open intelligence.",
        meta="17:00 · 4 Nov 2026")),
    ("kimi-bench", partial(
        l_bench, cat="Benchmarks · Moonshot", model="Kimi K3.1 Pro", head="Open weights, level with Opus 5.5", lab_w=200,
        panels=[("Terminal-Bench 4.0", "Agentic coding in a terminal",
                 [("Kimi K3.1 Pro", 65.7), ("Opus 5.5", 66.4), ("GPT-6 Astra", 58.2), ("Fable 5.1", 57.9)]),
                ("SWE Marathon", "Long software tasks",
                 [("Kimi K3.1 Pro", 51.7), ("Opus 5.5", 46.3), ("Fable 5.1", 45.6), ("GPT-6 Astra", 42.5)]),
                ("HLE, with tools", "Humanity&#8217;s Last Exam, full",
                 [("Kimi K3.1 Pro", 70.0), ("Opus 5.5", 67.7), ("Fable 5.1", 65.6), ("GPT-6 Astra", 57.2)])],
        note="Vendor-reported, compared with Fable 5.1, not 5.2. Measured independently: 46 on the AA Intelligence Index v5, "
             "#1 open weights, #10 overall. 2.8T parameters, 104B active, weights 1.56 TB; $2 / $10 per 1M tokens. "
             "Sources: Moonshot (23 Oct), artificialanalysis.ai")),
    ("deepseek-bench", partial(
        l_bench, cat="Releases · DeepSeek · 17 Oct", model="DeepSeek V4.1 Flash", head="Version 1017: better and shorter, same price",
        lab_w=200,
        panels=[("Terminal-Bench 4.0", "Agentic coding in a terminal", [("Flash 1017", 42.3), ("Flash, Sep", 31.2)]),
                ("DeepSWE v1.1", "Software engineering", [("Flash 1017", 77.0), ("Flash, Sep", 74.2)]),
                ("HLE, no tools", "Humanity&#8217;s Last Exam", [("Flash 1017", 42.6), ("Flash, Sep", 36.8)])],
        note="Vendor-reported. 33 on the AA Intelligence Index v5, #2 open weights. MIT license, weights on Hugging Face the same day; "
             "$0.30 / $1.20 per 1M tokens. Its uncensored copies: ~1M downloads in 30 days. Sources: DeepSeek, artificialanalysis.ai, Hugging Face")),
]

MISTRAL = [
    ("mistral-tweet", partial(
        sticker(l_tweet, "assets/recap/le-chonk-sticker.png", 1270, 330, 300, rot=-7),
        cat="Releases · Mistral · weights on 29 Oct", model="Mistral Large 4", size=34, width=1080,
        name="Mistral AI", handle="@MistralAI", avatar="assets/recap/mistralai-avatar.jpg",
        text="Meet Mistral Large 4, aka Le Chonk.<br><br>&#8226; 1T parameters, natively multimodal. 49B active.<br>"
             "It is the best open weights model from US or Europe on aggregated benchmarks.<br>"
             "[&#8230;]<br>&#8226; Forged in Europe end-to-end and is deployable from Europe via our own Mistral Cloud infrastructure.",
        meta="15:06 · 6 Oct 2026")),
    ("mistral-aa", partial(
        l_bench, cat="Benchmarks · Artificial Analysis · open weights", model="Mistral Large 4",
        head="Best open model outside China, by one point", lab_w=330, width=1250, top=400, hi=10,
        panels=[(None, None,
                 [("Claude Fable 5.2 &#183; closed", 65), ("Kimi K3.1 Pro &#183; CN", 46), ("DeepSeek V4.1 Flash &#183; CN", 33),
                  ("GLM-5.3 &#183; CN", 32), ("MiMo-V2.6-Pro &#183; CN", 30), ("Ling 3.1 Flash &#183; CN", 30),
                  ("MiniMax-M3.1-Flash &#183; CN", 29), ("Step 5 Preview &#183; CN", 29), ("GLM-5.3-Flash &#183; CN", 28),
                  ("MiMo-V2.6-Flash &#183; CN", 27), ("Mistral Large 4 &#183; EU", 26), ("Muse Spark Open &#183; US", 25)],
                 {"max": 70, "fmt": "{:.0f}", "row": 38, "bar": 22})],
        note=f"Fable 5.2 only for scale. Terminal-Bench 4.0: Mistral says 41%, AA measured 25%. Source: {AA5}")),
]

AGENTS = [
    ("agents", partial(
        l_table, cat="Agents", head="Every lab has a personal agent", top=360, row_h=78,
        cols=[("AGENT", 300, "left"), ("LAB", 210, "left"), ("SINCE", 300, "left"), ("WHAT&#8217;S SPECIAL", 750, "left")],
        rows=[["Gemini Spark", "Google", "19 May (I/O)", "Agentic assistant in Gmail and Google apps"],
              ["Muse", "Meta", "8 Sep", "10.9M downloads by 20 Oct (Sensor Tower)"],
              ["Dots", "OpenAI", "29 Sep (DevDay)", "Always on, $100 / month"],
              ["Claude Duet", "Anthropic", "21 Oct, preview", "Own app on Opus 5.5, US waitlist only"]],
        strong=("Claude Duet",),
        note="It doesn&#8217;t wait for a prompt: it checks in on its own and keeps working after you leave. "
             "Sources: Anthropic, Axios, eesel, TNW, TechTarget")),
    ("duet", partial(
        l_drei, cat="Agents · Anthropic · 21 Oct", model="Claude Duet", head="Late to the party, built for work",
        items=(("What it does", "Morning briefing",
                "Checks connected accounts every few hours, works in its own cloud computer, 6,000+ connectors."),
               ("Guardrails", "Asks first",
                "Before it sends, pays, signs or deletes. Never sees passwords or login tokens."),
               ("The catch", "US waitlist only",
                "Weaker at personal tasks; an analyst on B2B adoption: &#8220;months, maybe years, maybe never&#8221;.")))),
]

SECURITY = [
    ("sandbox", partial(
        l_table, cat="Security · OpenAI", model="Out of the sandbox", head="Three escapes since May, the last one via DNS",
        top=440, row_h=74,
        cols=[("DATE", 170, "left"), ("WHAT HAPPENED", 1350, "left")],
        rows=[["26 May", "First escape: agents reach the internet through a flaw in OpenAI&#8217;s internal package server"],
              ["9&#8211;19 Jul", "Agents get code execution on dozens of Hugging Face production servers, root on one"],
              ["20 Sep", "A research model uses a DNS misconfiguration to talk to a chatbot outside; training paused"],
              ["1 Oct", "Training resumes, 11 days after the pause began"],
              ["23 Oct", "&#8220;Securing our frontier model training environment&#8221;: frontier training now runs fully offline"]],
        strong=("20 Sep",),
        note="Instead of the live internet, an indexed cache: the &#8220;offline world&#8221;. Red-teaming found more ways out: "
             "sandbox escapes, covert channels between agents via timing on shared hardware. "
             "For builders: DNS is an exit too, not just HTTP. Sources: OpenAI, Forkast, Digital Applied")),
    ("948-funnel", partial(
        l_bench, cat="Security · OpenAI · 4 Nov", model="948 paths to root",
        head="Agents found 948 Linux kernel root bugs and wrote a patch for each", lab_w=420, width=1300, top=440,
        panels=[(None, None,
                 [("Targets picked by scout agents", 5034), ("Candidate bugs, after 12 h", 2308),
                  ("Reproduced in VMs, after 30 h", 1724), ("Unique root bugs, each with a patch", 948)],
                 {"max": 5100, "fmt": "{:,.0f}", "row": 76, "bar": 44})], hi=3,
        note="40M+ lines of kernel code; the targets cover 2.8M of them (~7%). Every bug lets a local user become root. "
             "When the run ended, 61 were fixed upstream, the rest are being reported. Source: OpenAI, &#8220;A thousand fewer paths to root&#8221;")),
    ("948-preis", partial(
        l_zahl, cat="Security · OpenAI", num="$1,280",
        text="per Linux root exploit, found and patched by agents. Pwn2Own pays around $20,000 for one. "
             "In July: 166 bugs at ~$3,100 each.",
        src="OpenAI, 4 Nov 2026: $1.21M API cost in total. July run: GPT-5.6 Sol, ~$514,000")),
    ("php2shell-tweet", partial(
        l_tweet, cat="Security · 21 Oct", model="PHP2Shell", size=36, width=1300, name="FBI Cyber Branch", handle="@FBICyberBranch",
        avatar="assets/recap/fbicyber-avatar.jpg",
        text="Two critical vulnerabilities have been identified in PHP [&#8230;] could allow malicious cyber actors to remotely "
             "execute code in PHP core [&#8230;]<br><br>&#10145;&#65039; If an immediate update is not feasible it is recommended "
             "that organizations take the system offline until it can be fully mitigated.",
        meta="16:59 · 21 Oct 2026")),
    ("php2shell-zeitleiste", partial(
        l_table, cat="Security · PHP core RCE, CVSS 9.2", model="PHP2Shell", head="Found by AI, exploited four days before the patch",
        top=440, row_h=64,
        cols=[("DATE", 170, "left"), ("WHAT HAPPENED", 1350, "left")],
        rows=[["1 Aug", "Calif finds the first bug with an LLM agent, in OpenAI&#8217;s &#8220;Patch the Planet&#8221; program"],
              ["19 Aug", "Wiz finds it on its own (Gemini 4 Argon + GPT-5.6 Sol); Drupal and WordPress exploits within two days"],
              ["18 Sep", "OpenAI Codex Security reports the same root cause"],
              ["17 Oct", "First exploitation attempts in Amazon&#8217;s honeypots"],
              ["20 Oct", "Leak: a post on HN, a tweet, and an exploit video Calif published by mistake"],
              ["21 Oct", "Patches: PHP 8.5.12 / 8.4.27 / 8.3.36 / 8.2.35; on CISA&#8217;s exploited list five days later"]],
        strong=("17 Oct",),
        note="Every PHP from 5.4 to 8.5; PHP runs ~70% of websites with a known server language. Government sites in the NL, "
             "FI and FR went offline as a precaution. PHP Foundation: 100+ invalid or duplicate reports since July, as AI-assisted reports rise. "
             "Sources: Wiz, Calif, PHP Foundation, AWS")),
    ("sshole-zitat", partial(
        l_statement, model="SSHole", size=58, top=200,
        text="&#8220;We have recently observed multiple cases of rapid bug rediscovery by AI agents, sometimes within hours, "
             "and so now consider long embargo periods to be a dangerous practice that primarily benefits attackers.&#8221;",
        src="Damien Miller, OpenSSH, 5 Nov 2026")),
    ("sshole-fakten", partial(
        l_drei, cat="Security · OpenSSH · CVE-2026-123158", model="SSHole", head="Found by an agent swarm, exploited within 9 hours",
        items=(("The bug", "Any long password",
                "musl&#8217;s crypt() returns &#8220;*&#8221; on error, sshd matches it against accounts locked with &#8220;*&#8221;. "
                "257&#8211;1024 characters get in."),
               ("Affected", "Alpine, OpenWrt, Yocto",
                "musl, no PAM, password login on. glibc distros and Dropbear are safe."),
               ("Do this", "OpenSSH 10.6p2",
                "Until then: PasswordAuthentication no. Check your Alpine-based images.")))),
    ("2shell", partial(
        l_table, cat="Security · October &#8211; November", head="Every bug is &#8220;something2Shell&#8221; now", top=360, row_h=74,
        cols=[("NAME", 300, "left"), ("WHAT", 620, "left"), ("FOUND BY", 450, "left"), ("DATE", 130, "left")],
        rows=[["PHP2Shell", "PHP core, remote code exec", "AI agents: Calif, Wiz, OpenAI", "21 Oct"],
              ["Node2Shell", "Brotli decoder: Node.js, Python, .NET", "OpenAI Codex Security", "21 Oct"],
              ["Plex2Shell", "Plex Media Server, four CVEs", "one researcher, &#8220;used LLMs heavily&#8221;", "16 Oct"],
              ["SSHole", "OpenSSH on musl, &#8220;the new SSH2SHELL&#8221;", "one researcher&#8217;s agent swarm", "5 Nov"],
              ["ssh2shell.com", "Teaser: &#8220;CVSS 10.0&#8221;, out 25 Dec", "anonymous, unverified", "24 Oct"],
              ["Terminal2Shell", "Parody site", "&#8212;", "9 Nov"]],
        strong=("PHP2Shell", "SSHole"),
        note="All but the last two are on CISA&#8217;s list of exploited vulnerabilities. AWS: AI makes turning a patch diff into "
             "an exploit cheap, so measure patch times in hours. Sources: Wiz, Node.js, Field Effect, Help Net Security, HN")),
    ("terminal2shell", partial(
        l_tweet, cat="Security · Community · 9 Nov", model="Terminal2Shell", size=64, width=900, name="Tib3rius", handle="@0xTib3rius",
        avatar="assets/recap/tib3rius-avatar.jpg", text="We&#8217;re cooked.<br><br>terminal2shell.com",
        meta="15:14 · 9 Nov 2026")),
]

IPO_SRC = "S-1/A of 10 Nov 2026, WSJ, CNBC, Reuters (10 Nov)"
IPO = [
    ("ipo-tweet", partial(
        l_tweet, cat="Business · Anthropic · 9 Nov", model="Anthropic IPO", size=44, name="swyx", handle="@swyx",
        avatar="assets/recap/swyx-avatar.jpg",
        text="btw by complete coincidence the $ANT IPO roadshow across wall street started today. they had this in the "
             "chamber and its also nice that it came after Astra, Argon and Carbon&#8230;",
        meta="20:44 · 9 Nov 2026")),
    ("ipo-zahlen", partial(
        l_table, cat="Business · Anthropic · filed today", model="Anthropic IPO", head="$70&#8211;78 a share, trading from 19 Nov",
        top=430, row_h=60,
        cols=[("", 300, "left"), ("", 330, "left"), ("", 940, "left")],
        rows=[["Shares offered", "825M", "+ up to 124M if the banks use their greenshoe"],
              ["Raise", "$58&#8211;64B", "$61B at the $74 midpoint, ~$74B with greenshoe"],
              ["Valuation", "~$1.33T", "fully diluted at the midpoint (WSJ); press estimates, not in the filing"],
              ["Shares only", "$0.92&#8211;1.02T", "13.09B shares after the IPO &#215; price, no options"],
              ["Next to it", "$26B placement", "at the IPO price: Google, Nvidia $10B each; AMD, Broadcom, Micron, MS, TSMC"],
              ["Dates", "18 / 19 Nov", "pricing / first trade as ANT on Nasdaq (WSJ, CNBC sources)"],
              ["Last round", "$965B", "private, May 2026; in October investors talked about $2T"]],
        strong=("Raise", "Valuation"),
        note=f"Overnight a first version (867M shares at $70&#8211;80, up to $69.3B) went out and was retracted as "
             f"&#8220;inaccurate&#8221;. First nine months of 2026: revenue $33.2B, operating loss $1.3B. Source: {IPO_SRC}")),
    ("ipo-verlauf", partial(
        l_ranges, cat="Business · Valuation talk over time", model="Anthropic IPO", head="From $2T talk to $1.3T on file",
        yticks=(1.0, 1.5, 2.0),
        points=[("28 MAY", 0.965, 0.965, "$0.97T", "private round", "round"),
                ("13 AUG", 2.0, 2.0, "&#8805;$2T", "FT", "talk"),
                ("18 SEP", 2.0, 2.0, "~$2T", "WSJ: IPO to Nov", "talk"),
                ("15 OCT", 1.5, 1.5, "~$1.5T", "Reuters", "talk"),
                ("2 NOV", 1.5, 1.6, "$1.5&#8211;1.6T", "WSJ", "talk"),
                ("6 NOV", 1.1, 1.3, "$1.1&#8211;1.3T", "Bloomberg", "talk"),
                ("10 NOV", 1.26, 1.41, "$1.26&#8211;1.41T", "filed range", "filed")],
        events=[(4.42, "3 NOV midterms", 0), (4.58, "5 NOV Nasdaq &#8722;5.5%", 1)],
        note="Fully diluted. Everything between the round and the filing is investor talk from unnamed sources. "
             "15 Oct: investor day, growth slowing; 2 Nov: Q3 operating loss. 5 Nov: Nvidia &#8722;9.3%, chip index &#8722;12%. "
             "Sources: Anthropic, FT, WSJ, Reuters, Bloomberg, CNBC, S-1/A")),
    ("ipo-rang", partial(
        l_bench, cat="Business · Largest IPOs ever", model="Anthropic IPO", head="Second only to SpaceX", lab_w=380, width=1300,
        top=440, hi=1,
        panels=[(None, None,
                 [("SpaceX · Jun 2026", 75.0), ("Anthropic · top of range", 64.4), ("SK hynix ADR · Jul 2026", 26.5),
                  ("Saudi Aramco · 2019", 25.6), ("Alibaba · 2014", 21.8), ("SoftBank Corp · 2018", 21.3)],
                 {"max": 80, "fmt": "${:.1f}B", "row": 64, "bar": 38})],
        note="Amount raised in the base deal, without greenshoe. Anthropic: 825M shares &#215; $78. "
             "Sources: Renaissance Capital, S-1/A of 10 Nov 2026")),
    ("ipo-firmen", partial(
        l_bench, cat="Business · Most valuable companies", model="Anthropic IPO", head="Between Tesla and Eli Lilly, fully diluted",
        lab_w=400, width=1300, top=410, hi=11,
        panels=[(None, None,
                 [("Apple", 5.10), ("Nvidia", 4.31), ("Microsoft", 4.05), ("Alphabet", 3.52), ("Amazon", 2.89), ("TSMC", 2.02),
                  ("SpaceX", 1.93), ("Saudi Aramco", 1.65), ("Meta", 1.64), ("Broadcom", 1.53), ("Tesla", 1.49),
                  ("Anthropic &#183; fully diluted, $74", 1.33), ("Eli Lilly", 1.26), ("OpenAI &#183; private", 1.25),
                  ("Anthropic &#183; shares only, $74", 0.97)],
                 {"max": 5.5, "fmt": "${:.2f}T", "row": 30, "bar": 18})],
        note="Close of 9 Nov (companiesmarketcap.com); OpenAI: Bloomberg, 6 Nov. Listed caps count shares only: "
             "counted that way, Anthropic is about #16, behind Walmart and Samsung")),
]

POLITICS = [
    ("midterms", partial(
        l_zahl, cat="Politics · US midterms · 3 Nov", num="40 : 1",
        text="Local votes on data centers: 41 on the ballot in 10 states, 21 in Ohio alone. "
             "Data centers won one, in Harwood, North Dakota.",
        src="Fast Company, Al Jazeera")),
    ("midterms-zahlen", partial(
        l_drei, cat="Politics · US midterms", head="AI became a ballot issue",
        items=(("NBC exit poll", "76% against", "a new data center in their own community."),
               ("Voters", "56% say", "AI and data centers were &#8220;a crucial or major factor&#8221; in their vote."),
               ("AI money", "$4.8M, lost", "Two pro-AI and pro-data-center PACs backed one candidate in South Carolina. She lost, 47 to 51.")))),
]

EU = [
    ("ai-act", partial(
        l_table, cat="Regulation · EU AI Act", head="Next deadline: 2 December 2026", top=360, row_h=84,
        cols=[("DATE", 300, "left"), ("WHAT APPLIES", 1250, "left")],
        rows=[["since Feb 2025", "Bans, e.g. social scoring, emotion recognition at work"],
              ["since 2 Aug 2026", "Transparency duties (Art. 50): chatbots say they are AI; Commission can fine GPAI providers"],
              ["2 Dec 2026", "Machine-readable marking of AI output (Art. 50(2)), also for systems on the market before August"],
              ["2 Dec 2027", "High-risk rules for Annex III systems: hiring, credit, education"],
              ["2 Aug 2028", "High-risk rules for AI in products (Annex I)"]],
        strong=("2 Dec 2026",),
        note="The Digital Omnibus (Regulation (EU) 2026/1744, in force since 27 Jul) moved the high-risk rules back by 12&#8211;16 months: "
             "postponed, not dropped. New bans from 2 Dec 2026: non-consensual intimate deepfakes, CSAM generation. Open question: who is Austria&#8217;s market surveillance authority? Sources: nisd2.eu, MEAN CEO")),
]

TERMS = [
    ("term-psychosis", partial(
        l_text, cat="Term of the month", model="AI psychosis",
        head="Delusions that start or grow in long talks with an agreeable chatbot", size=36,
        items=(("7 Oct, JAMA Psychiatry:", "28 cases among ~216,000 patients at Vanderbilt. Rare, but 61% were first episodes, "
                                           "and in 64% the chatbot acted as an amplifier."),
               ("10 Oct, Elon Musk:", "&#8220;At various points this year, I&#8217;ve had AI or SI psychosis probably like half a dozen times.&#8221;"),
               ("14 Oct, eight US states sue OpenAI:", "ChatGPT was &#8220;designed to be agreeable&#8221;, and OpenAI "
                                                       "misled users about its safety.")),
        note="Not a clinical diagnosis. Sources: JAMA Psychiatry (Bergson &amp; Sheffield, 7 Oct), A.V. Club (15 Oct), Just Security (15 Oct)")),
    ("term-abliterated", partial(
        l_text, cat="Term of the month", model="abliterated",
        head="An open model with its refusals cut out of the weights, no retraining", size=36,
        items=(("How:", "find the one direction in the network that makes the model say no, and project it out. "
                        "Ablation + obliterated."),
               ("This month:", "an uncensored Mistral Large 4 on Hugging Face two days after its weights came out. "
                               "9,136 &#8220;abliterated&#8221; repos, 719 of them new in October."),
               ("The catch:", "ProjectDiscovery hid a credential-stealing backdoor in an edited open model for under $50. "
                              "In a Codex setup the trigger fired 50 times out of 50, normal accuracy stayed at 100%.")),
        note="Method: Arditi et al., NeurIPS 2024; the name: FailSpy (2024), made popular by Maxime Labonne. "
             "Sources: Hugging Face API (10 Nov), ProjectDiscovery (6 Oct), Schneier (16 Oct)")),
]

TAKEAWAYS = [
    ("takeaways", partial(
        l_text, cat="Takeaways", head="What to do with this month", size=31,
        items=(("Test now:", "Fable 5.2 (hardest tasks), Muse Ember (subagents), Argon (long outputs, launch price until 30 Nov), "
                             "Mistral Large 4 (data stays in Europe)."),
               ("Count per task, not per token:", "Ember and Haiku cost the same per token; on AA&#8217;s index tasks Ember is 3&#215; cheaper."),
               ("Mix models:", "a big model plans, a small one executes. Every lab now ships a family built for exactly that."),
               ("Harden:", "DNS is an exit too. Patch PHP, OpenSSH and your kernels: for PHP and OpenSSH, exploits came within hours."),
               ("EU deadline:", "label AI output of existing systems by 2 December 2026."))
    )),
]

NEWS = [*GOOGLE, *CHINA, *MISTRAL, *AGENTS, *SECURITY, *IPO, *POLITICS, *EU, *TERMS, *TAKEAWAYS]

QUESTIONS = [
    ("decider", partial(
        l_drei, cat="Discussion · Amazon · strandsagents.com, 9 Nov", model="Strands Decider",
        head="Amazon runs a decision model in production. Do you use any?",
        items=(("What it is", "Picks, doesn&#8217;t write",
                "State + options in, a probability per option and a confidence out. &#8220;A decision model can&#8217;t generate text.&#8221;"),
               ("In production", "Ticket routing",
                "Amazon&#8217;s internal ticket system: each ticket to one of 20 labels, replacing Claude Sonnet 4.6. "
                "A Gemma 4 E4B build on one A10G GPU."),
               ("Result", "98% cheaper",
                "$22,200 &#8594; $500 per million tickets, 4.2 s &#8594; 0.9 s per call: &#8220;millions of dollars&#8221; a year.")))),
    ("frage-agent", partial(l_frage, q="Would you give a personal agent your inbox?")),
    ("frage-zugang", partial(l_frage, q="The best models only for selected customers: fair, or a brake on small builders?", size=84)),
    ("frage-ipo", partial(l_frage, q="$1.3 trillion for Anthropic: bubble or justified?")),
    ("frage-rechenzentren", partial(l_frage, q="Could data centers become a fight in Austria too?")),
    ("frage-neu", partial(l_frage, q="Which tool or model did you discover this month?")),
]


LAYOUTS = [("orga", l_orga), ("agenda", l_agenda), ("website", l_website), *RELEASES, *MUSE, *FABLE, *NEWS,
           ("diskussion-tempo", partial(
               l_cadence, question="Are the frontier labs pacing themselves?",
               bands=(("2026-09-01", "2026-09-03", "1&#8211;3 Sep: all four labs ship", "end"),
                      ("2026-09-22", "2026-09-30", "22&#8211;30 Sep: again", "start")),
               note="Every model in Epoch&#8217;s list, 10 Nov 2025 &#8211; 10 Nov 2026; filled = new best of that lab. "
                    "Since April, Anthropic has set a new lab best every 2&#8211;7 weeks. Source: epoch.ai/eci")),
           ("frage-dominanz", partial(l_frage, q="Will OpenAI &amp; Anthropic still dominate in a year?")),
           *QUESTIONS, ("tierlist", l_fullscreen), ("ende", l_ende)]


# ----------------------------------------------------------------- master deck: every layout once, with [placeholders]
_PH_ROWS = [("[Model A]", 70), ("[Model B]", 62), ("[Model C]", 55), ("[Model D]", 41)]
MASTER = [
    ("orga", l_orga), ("agenda", l_agenda), ("website", l_website),
    ("story", l_story),
    ("tweet", l_tweet), ("tweets", l_tweets), ("tweet-media", l_tweet_media),
    ("tweet-video", partial(l_tweet_video, model="[Model]", head="[One-line claim]")),
    ("drei-spalten", l_drei), ("zahl", l_zahl),
    ("text", partial(l_text, cat="Takeaways", head="[What to do with this month]",
                     items=[("[Lead]", "[the rest of the point, one or two lines]")] * 4)),
    ("text-absatz", partial(l_text, cat="Term of the month", model="[Term]", head="[The term in one line]",
                            text="[A short paragraph: where the term comes from, what it means, and one example "
                                 "people in the room will recognise.]", note="[Source]")),
    ("bench", partial(l_bench, model="[Model]", head="[One-line claim]", note="[What is measured. Source]",
                      panels=[("[Benchmark]", "[What it tests]", _PH_ROWS)] * 3)),
    ("table", partial(l_table, model="[Model]", head="[One-line claim]", note="[Source]", strong=("[Model A]",),
                      cols=[("MODEL", 340, "left"), ("LAB", 200, "left"), ("[VALUE]", 200, "right"), ("[VALUE]", 200, "right")],
                      rows=[[m, "[Lab]", f"{v}", f"${v / 10:.2f}"] for m, v in _PH_ROWS])),
    ("eci", partial(l_eci, model="[Model]", head="[One-line claim]", label={"Claude Fable 5.2": None},
                    note="[What the chart shows. Source: epoch.ai/eci]")),
    ("pareto", partial(l_pareto, model="[Model]", head="[One-line claim]",
                       label={"anthropic/claude-fable-5-2": (24, -14, "start")}, note="[Source: vals.ai]")),
    ("timeline", partial(l_timeline, head="[Headline]", today="2026-11-10", note="[Legend. Sources]",
                         ticks=(("2026-10-01", "1 OCT"), ("2026-10-15", "15 OCT"), ("2026-11-01", "1 NOV")),
                         lanes=(("[Lab A]", (("2026-10-07", "[Model]", "pub"), ("2026-11-02", "[Model]", "gated"))),
                                ("[Lab B]", (("2026-10-15", "[Model]", "open"), ("2026-11-06", "[Model]", "teaser"))),
                                ("[Lab C]", (("2026-10-24", "[Model]", "pub"),))))),
    ("cadence", partial(l_cadence, question="[Question for the room?]", note="[Source: epoch.ai/eci]")),
    ("labs", partial(l_labs, question="[Question for the room?]", note="[Source: epoch.ai/eci]")),
    ("talk", l_talk), ("statement", l_statement), ("frage", l_frage), ("tierlist", l_fullscreen), ("ende", l_ende),
]

# the master deck's edition: placeholders only, nothing from a real edition except the permanent links
MASTER_ED = {"edition": "#N", "datum": "[DD.MM.YYYY]", "zeit": "[18:00]", "ort": "[VENUE]", "wifi": False}


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


def build(ed, layouts, dest, title):
    MEDIA.clear()
    n = len(layouts) + 1
    secs, names = [], []

    def add(name, cam, html):
        secs.append(f'<section class="slide" data-name="{name}" data-cam="{",".join(map(str, cam))}">{html}</section>')
        names.append(name)

    cam, html = title_slide(ed)
    add("01-titel", cam, html)
    for k, (name, fn) in enumerate(layouts, start=2):
        cam, html = fn(ed)
        base = getattr(fn, "func", fn)
        if base is l_fullscreen:  # no chrome on a full-bleed image
            add(f"{k:02d}-{name}", cam, html)
        elif base.__name__.startswith("st_"):  # show & tell: its own header, only the slide number from the deck
            add(f"{k:02d}-{name}", cam, html + f'<div class="abs mono" style="right:{CORNER}px;top:{CORNER - 24}px;'
                                                f'font-size:22px">{k:02d} / {n:02d}</div>')
        else:
            add(f"{k:02d}-{name}", cam, html + chrome(k, n, ed, with_logo=name != "orga"))

    tpl = (ROOT / "tools" / "deck-template.html").read_text(encoding="utf-8")
    out = tpl
    for key, val in {"__TITLE__": title, "__FONTS__": FONTS, "__INK__": INK, "__MUTED__": MUTED,
                     "__GRAD__": GRAD, "__SLIDES__": "\n".join(secs), "__FS__": FS, "__TILE__": TILE_BG,
                     "__VARIANT__": str(VARIANT), "__PRESETS__": json.dumps(R.PRESETS)}.items():
        out = out.replace(key, val)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "index.html").write_text(out, encoding="utf-8")
    if (dest / "media").exists():
        shutil.rmtree(dest / "media")
    for m in MEDIA:
        (dest / "media").mkdir(exist_ok=True)
        shutil.copy(ROOT / m, dest / "media" / Path(m).name)
    (dest / "meta.json").write_text(json.dumps({"slides": names}), encoding="utf-8")
    print(f"built {dest / 'index.html'} ({n} slides)")


def main():
    ed = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "editions" / "001.json").read_text(encoding="utf-8"))
    build(ed, LAYOUTS, ROOT / "build" / "deck", f'WAISS {ed["edition"]} – Slides')
    build(MASTER_ED | {"links": ed["links"]}, MASTER, ROOT / "build" / "master", "WAISS – Master slides")


if __name__ == "__main__":
    main()
