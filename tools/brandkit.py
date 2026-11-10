#!/usr/bin/env python3
"""WAISS brand kit: logos, wordmark, icon, colours, fonts and blob renders in one folder.

    python -X utf8 tools/brandkit.py     # npm run brandkit
    -> assets/logo/waiss-*            master files (blob mark, lockups, wordmark SVG)
    -> exports/brand-kit/             the kit, with index.html as overview
    -> exports/waiss-brand-kit.zip    the same folder as one download

Sources: the blob shader (design/canvas/Blob.dc.html via tools/deck.py, variant 0 like the deck), the Secession
glyphs (design/canvas/Txt.dc.html), the W icon (tools/site.py favicon(), PNGs in assets/icons/), the colour tokens
in tools/site.css and the fonts in assets/fonts/. tools/brandkit.js renders the blob and rasterises SVGs (Playwright,
SwiftShader): every run gives the same files.
"""
import importlib.util, json, re, shutil, subprocess, zipfile
from pathlib import Path
from PIL import Image

import deck as D
import render as R

ROOT = R.ROOT
LOGO = ROOT / "assets" / "logo"
KIT = ROOT / "exports" / "brand-kit"
TMP = ROOT / "build" / "brandkit"
_spec = importlib.util.spec_from_file_location("waiss_site", ROOT / "tools" / "site.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

ROT = 120      # the mark: variant 0 turned so the spikes stand out of the silhouette and the long one points up
RENDER = 2048  # blob render size; outputs are scaled down from it
WORD_H = 400   # letter height of the wordmark in the PNG lockups
FONTS = {"Tektur": "tektur", "Archivo": "archivo", "IBM Plex Mono": "ibmplexmono"}  # brand fonts (not the hackathon chips)
ROLES = {  # tools/site.css token -> (name, use)
    "bg": ("Off-White", "Hintergrund, Flächen"),
    "ink": ("Tinte", "Text, Wortmarke, Linien. Die einzige dunkle Farbe."),
    "muted": ("Grau", "Nebentext, Daten, Bildunterschriften"),
    "tile": ("Kachel", "Karten und Kacheln auf dem Hintergrund"),
    "line": ("Linie", "Rahmen, Trennlinien"),
}


def colours():
    css = (ROOT / "tools" / "site.css").read_text(encoding="utf-8")
    root = re.search(r":root\{(.*?)\}", css, re.S).group(1)
    tokens = dict(re.findall(r"--([\w-]+):(#[0-9A-Fa-f]{6})", root))
    return {k: {"hex": tokens[k].upper(), "name": n, "use": u} for k, (n, u) in ROLES.items()}


def wordmark(text, colour):
    """Secession lettering as one SVG: glyph cells 100 high, gap 0.2 x height, stroke 16, like render.txt()."""
    x, paths = 0, []
    for ch in text:
        vx, w, d = R.G[ch]
        paths.append(f'<path transform="translate({x - vx:g} 0)" d="{d}"/>')
        x += w + 20
    p = 12  # half the stroke plus miter tips
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-p} {-p} {x - 20 + 2 * p:g} {100 + 2 * p}" role="img" '
            f'aria-label="{text}"><title>{text}</title><g fill="none" stroke="{colour}" stroke-width="16" '
            f'stroke-linejoin="miter">{"".join(paths)}</g></svg>')


def alphabet(colour):
    """Every Secession glyph, ten per row."""
    chars = [c for c in R.G if c.strip() and c.isascii()]
    chars = sorted(chars, key=lambda c: (not c.isalpha(), not c.isdigit(), c))
    cell, rows = 150, []
    for i, ch in enumerate(chars):
        vx, w, d = R.G[ch]
        cx, cy = (i % 10) * cell + (cell - w) / 2, (i // 10) * cell + 25
        rows.append(f'<path transform="translate({cx - vx:g} {cy:g})" d="{d}"/>')
    h = ((len(chars) + 9) // 10) * cell
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {10 * cell} {h}" role="img" aria-label="Secession-Alphabet">'
            f'<g fill="none" stroke="{colour}" stroke-width="16" stroke-linejoin="miter">{"".join(rows)}</g></svg>')


def render(svgs):
    TMP.mkdir(parents=True, exist_ok=True)
    views = [{"name": "mark", "preset": R.PRESETS[D.VARIANT], "rot": ROT, "zoom": 0.62}]
    views += [{"name": f"variante-{i}", "preset": p, "rot": 0, "zoom": 0.62} for i, p in enumerate(R.PRESETS)]
    job = {"fs": D.FS, "size": RENDER, "out": str(TMP), "views": views, "svgs": svgs}
    (TMP / "job.json").write_text(json.dumps(job), encoding="utf-8")
    subprocess.run(["node", str(ROOT / "tools" / "brandkit.js"), str(TMP / "job.json")], check=True, cwd=ROOT)
    out = {n: Image.open(TMP / f"{n}.png").convert("RGBA") for n in [v["name"] for v in views] + [s["name"] for s in svgs]}
    assert len({out[v["name"]].tobytes() for v in views}) == len(views), "blob views came out identical"
    return out


def square(im, pad):
    """Crop to the visible pixels, centred in a square with `pad` (fraction of the side) free on every edge."""
    l, t, r, b = im.getchannel("A").point(lambda a: 255 if a > 4 else 0).getbbox()
    side = round(max(r - l, b - t) / (1 - 2 * pad))
    sq = Image.new("RGBA", (side, side))
    sq.alpha_composite(im.crop((l, t, r, b)), ((side - (r - l)) // 2, (side - (b - t)) // 2))
    return sq


def lockup(blob, word):
    """Blob left, wordmark right: the blob 1.9x the letter height, both centred on one line."""
    word = word.crop(word.getchannel("A").getbbox())
    bm = square(blob, 0).resize((round(WORD_H * 1.9),) * 2, Image.LANCZOS)
    gap, pad = round(WORD_H * 0.55), round(WORD_H * 0.25)
    im = Image.new("RGBA", (pad + bm.width + gap + word.width + pad, bm.height + 2 * pad))
    im.alpha_composite(bm, (pad, pad))
    im.alpha_composite(word, (pad + bm.width + gap, pad + (bm.height - word.height) // 2))
    return im


def scaled(im, width):
    return im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)


def main():
    col = colours()
    ink, bg = col["ink"]["hex"], col["bg"]["hex"]
    svg = {"waiss-wortmarke": wordmark("WAISS", ink), "waiss-wortmarke-hell": wordmark("WAISS", bg),
           "secession-alphabet": alphabet(ink)}
    word_w = lambda s: round(float(re.search(r'viewBox="\S+ \S+ (\S+)', s).group(1)) * WORD_H / 100)
    im = render([{"name": n, "svg": s, "width": word_w(s)} for n, s in svg.items() if n != "secession-alphabet"])

    # master files (others link to these paths)
    LOGO.mkdir(parents=True, exist_ok=True)
    mark = square(im["mark"], 0.03)
    files = {
        "waiss-blob.png": mark.resize((1024, 1024), Image.LANCZOS),
        "waiss-lockup.png": lockup(im["mark"], im["waiss-wortmarke"]),
        "waiss-lockup-hell.png": lockup(im["mark"], im["waiss-wortmarke-hell"]),
    }
    for n, f in files.items():
        f.save(LOGO / n)
    for n in ("waiss-wortmarke", "waiss-wortmarke-hell"):
        (LOGO / f"{n}.svg").write_text(svg[n], encoding="utf-8")

    # the kit
    if KIT.exists():
        shutil.rmtree(KIT)
    for d in ("logo", "icon", "blob", "farben", "schrift/desktop", "schrift/web", "secession", "telos-circle"):
        (KIT / d).mkdir(parents=True)
    for n in ("waiss-lockup", "waiss-lockup-hell"):
        files[n + ".png"].save(KIT / "logo" / f"{n}.png")
        scaled(files[n + ".png"], 1200).save(KIT / "logo" / f"{n}-1200.png")
    for n in ("waiss-wortmarke", "waiss-wortmarke-hell"):
        (KIT / "logo" / f"{n}.svg").write_text(svg[n], encoding="utf-8")
        im[n].save(KIT / "logo" / f"{n}.png")
    mark.resize((2048, 2048), Image.LANCZOS).save(KIT / "logo" / "waiss-blob-2048.png")
    files["waiss-blob.png"].save(KIT / "logo" / "waiss-blob-1024.png")
    mark.resize((512, 512), Image.LANCZOS).save(KIT / "logo" / "waiss-blob-512.png")

    (KIT / "icon" / "waiss-w.svg").write_text(S.favicon(), encoding="utf-8")
    icons = ROOT / "assets" / "icons"
    for f in sorted(icons.glob("*.png")):
        shutil.copy(f, KIT / "icon" / f.name.replace("icon-", "waiss-w-").replace("apple-touch-icon", "waiss-w-180-apple-touch"))
    with Image.open(icons / "icon-48.png") as big:
        big.save(KIT / "icon" / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)],
                 append_images=[Image.open(icons / f"icon-{px}.png") for px in (16, 32)])

    for i in range(len(R.PRESETS)):
        square(im[f"variante-{i}"], 0.03).resize((1600, 1600), Image.LANCZOS).save(KIT / "blob" / f"waiss-blob-variante-{i}.png")

    (KIT / "farben" / "farben.json").write_text(json.dumps({**col, "gradient": D.GRAD}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (KIT / "farben" / "farben.css").write_text(
        ":root {\n" + "".join(f"  --waiss-{k}: {v['hex']}; /* {v['name']}: {v['use']} */\n" for k, v in col.items())
        + f"  --waiss-gradient: {D.GRAD};\n}}\n", encoding="utf-8")

    for fam, d in FONTS.items():
        shutil.copytree(ROOT / "assets" / "fonts" / "desktop" / d, KIT / "schrift" / "desktop" / d)
    css = (ROOT / "assets" / "fonts" / "fonts.css").read_text(encoding="utf-8")
    keep = [b for b in re.split(r"(?=/\* )", css) if any(f"/* {fam} " in b for fam in FONTS)]
    for b in keep:
        for f in re.findall(r"url\(([^)]+\.woff2)\)", b):
            shutil.copy(ROOT / "assets" / "fonts" / f, KIT / "schrift" / "web" / f)
    (KIT / "schrift" / "web" / "fonts.css").write_text("".join(keep).rstrip() + "\n", encoding="utf-8")

    (KIT / "secession" / "secession-alphabet.svg").write_text(svg["secession-alphabet"], encoding="utf-8")
    for f in sorted(LOGO.glob("telos-circle*.svg")):
        shutil.copy(f, KIT / "telos-circle" / f.name)

    page = (ROOT / "tools" / "brandkit-template.html").read_text(encoding="utf-8")
    swatches = "".join(
        f'<div class="sw"><div class="chip" style="background:{v["hex"]}"></div><b>{v["name"]}</b>'
        f'<code>{v["hex"]}</code><code>--waiss-{k}</code><span>{v["use"]}</span></div>' for k, v in col.items())
    page = (page.replace("__SWATCHES__", swatches).replace("__GRAD__", D.GRAD)
            .replace("__WORDMARK__", svg["waiss-wortmarke"]).replace("__ALPHABET__", svg["secession-alphabet"]))
    (KIT / "index.html").write_text(page, encoding="utf-8")
    shutil.copy(ROOT / "tools" / "brandkit-readme.md", KIT / "README.md")

    z = ROOT / "exports" / "waiss-brand-kit.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(KIT.rglob("*")):
            if f.is_file():  # fixed timestamps: the zip stays byte-identical when nothing changed
                zf.writestr(zipfile.ZipInfo(str(Path("waiss-brand-kit") / f.relative_to(KIT)).replace("\\", "/"),
                                            (2026, 1, 1, 0, 0, 0)), f.read_bytes(), zipfile.ZIP_DEFLATED)
    n = sum(1 for f in KIT.rglob("*") if f.is_file())
    print(f"wrote assets/logo/waiss-*, {KIT.relative_to(ROOT)} ({n} files), {z.relative_to(ROOT)} ({z.stat().st_size >> 10} KB)")


if __name__ == "__main__":
    main()
