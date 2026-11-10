#!/usr/bin/env python3
"""Download the deck's Google Fonts once into assets/fonts/ (woff2 + fonts.css), so the website serves them
itself and visitors never contact Google (GDPR). Run again only when tools/deck.py's FONTS change.

    python3 tools/fetch-fonts.py
"""
import re, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from deck import FONTS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "fonts"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
KEEP = {"latin", "latin-ext"}  # German + English; drop cyrillic, greek, vietnamese, ...


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA})).read()


def main():
    css = get(re.search(r'href="([^"]+)"', FONTS).group(1).replace("&amp;", "&")).decode()
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.woff2"):
        f.unlink()
    out = []
    for subset, block in re.findall(r"/\* ([\w-]+) \*/\s*(@font-face \{.*?\})", css, re.S):
        if subset not in KEEP:
            continue
        fam = re.search(r"font-family: '([^']+)'", block).group(1)
        style = re.search(r"font-style: (\w+)", block).group(1)
        weight = re.search(r"font-weight: ([\d ]+);", block).group(1).replace(" ", "-")
        url = re.search(r"url\((https://[^)]+\.woff2)\)", block).group(1)
        name = f"{fam.lower().replace(' ', '-')}-{style}-{weight}-{subset}.woff2"
        if not (OUT / name).exists():
            (OUT / name).write_bytes(get(url))
        out.append(f"/* {fam} {subset} */\n" + block.replace(url, name))
    (OUT / "fonts.css").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {len(out)} faces, {len(list(OUT.glob('*.woff2')))} files to {OUT}")


if __name__ == "__main__":
    main()
