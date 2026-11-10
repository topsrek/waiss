# WAISS Brand Kit

WAISS = **W**iener **AI** **S**oftware **S**tammtisch, gesprochen wie „weiß“. Ein Format von Telos Circle.
Die Übersicht mit Beispielen steht in `index.html` (im Browser öffnen).

| Ordner | Inhalt |
|---|---|
| `logo/` | Lockup Blob + Wortmarke (`waiss-lockup*.png`, Tinte und hell), Wortmarke als SVG/PNG, Bildmarke Blob 512/1024/2048 px |
| `icon/` | W-Icon: `waiss-w.svg`, PNG 16–512, `favicon.ico`, Apple-Touch 180 |
| `blob/` | die vier Blob-Varianten, 1600 px, transparent |
| `farben/` | `farben.css`, `farben.json` |
| `schrift/` | `desktop/`: TTF zum Installieren (+ OFL-Lizenz), `web/`: WOFF2 + `fonts.css` |
| `secession/` | das Secession-Alphabet als SVG |
| `telos-circle/` | Telos-Circle-Logos für den Absender |

## Kurz

- **Farben:** Off-White `#F5F3EE`, Tinte `#1F1E1B`, Grau `#66635C`, Kachel `#FCFBF8`, Linie `#C9C5BB`. Keine Akzentfarbe.
- **Schrift:** Tektur 800 für Überschriften, Archivo für Fließtext, IBM Plex Mono für Kleingedrucktes. Die Wortmarke ist
  das eigene Secession-Alphabet (keine Schriftdatei).
- **Blob** erst ab etwa 128 px, darunter das **W-Icon**.
- Lockup auf hellem Grund in Tinte, auf dunklem Grund die helle Variante.

Erzeugt aus dem WAISS-Repo mit `npm run brandkit` (`tools/brandkit.py`). Nicht von Hand ändern.
