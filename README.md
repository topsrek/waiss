# WAISS – Wiener AI Software Stammtisch

A cozy get-together, planned monthly, for everyone in Vienna who builds, codes & experiments with AI.
Organized by [Telos Circle](https://www.teloscircle.com).

Every meetup starts with a ~20 min **AI recap** of the past month, followed by short talks
(tool tips, show & tell) and an open round.

| | |
|---|---|
| **#1** | Tue 10 Nov 2026, 18:00 · Café Ritter, Mariahilfer Str. 73, 1060 Wien |
| **Sign up** | https://luma.com/ba5jlhla |

![Luma cover #1](exports/001/luma-cover.png)

## What's in here

```
design/canvas/   Source of truth: the design canvas files (*.dc.html) – blob, flyers, slides, wordmark
assets/logo/     Telos Circle logo (column, wordmark, "by" lockup) as clean SVGs
editions/        One JSON per meetup (edition, date, time, venue, sign-up link)
texts/           Announcement texts per edition (WhatsApp DE/EN, Luma)
exports/         Rendered PNGs per edition
tools/           render.py + screenshot.js – flyers; deck.py + export-deck.js – the slide deck
docs/brand.md    Colors, wordmark, blob parameters, layout rules
```

## Rendering the flyers for an edition

Requirements: Python 3, Node 18+, Playwright (`npm install`, then `npx playwright install chromium`).

```bash
cp editions/001.json editions/002.json   # edit edition, date, time, venue, link
python3 tools/render.py editions/002.json             # -> build/002/*.html
node tools/screenshot.js build/002 exports/002        # -> PNGs
node tools/screenshot.js build/002 exports/002 2      # -> @2x PNGs
```

The `.dc.html` files use the design canvas' template syntax (`{{holes}}`, `<dc-import>`,
`data-props`). `render.py` resolves it without the canvas runtime: Secession text becomes
inline SVG, the blob becomes a `<canvas>` with the WebGL shader from `Blob.dc.html`.

## Slides

`python3 -X utf8 tools/deck.py` builds `build/deck/index.html`: one self-contained presentation where the
same blob rotates and travels between slides. Arrow keys / space / click to navigate, `F` fullscreen,
`#N` jumps to slide N. `node tools/export-deck.js` writes PNGs and the PDF fallback to `exports/deck/`
(`npm run deck` does both). Needs `pip install qrcode` for the QR codes. Layouts are the functions in
`tools/deck.py`; links and the optional `wifi` (`{"ssid", "password"}`) come from `editions/*.json`.

## Roadmap

- [ ] Slides website: the monthly recap as HTML slides with the blob in the background,
      reacting to slide changes. Others can contribute slides via pull request.
- [ ] Slide generator: one folder per edition, blob transitions between slides.
- [ ] Flyer generator for the next editions directly from `editions/*.json`.
