# WAISS – Branding

**WAISS** = **W**iener **AI** **S**oftware **S**tammtisch, gesprochen wie „weiß“.
Ein Format von Telos Circle. Erstes Treffen: #1, Di 10.11.2026, 18:00, Café Ritter (Mariahilfer Str. 73).

## Farben

| Rolle | Wert |
|---|---|
| Hintergrund (Off-White) | `#F5F3EE` |
| Tinte (Text, Logo) | `#1F1E1B` |
| Blob | Weiß/Creme, glänzend, leicht graue Schatten |

Alles bleibt in Weiß-, Off-White- und Cremetönen. Schwarz kommt nur als Tinte vor.

## Wortmarke und Schrift

- **Secession-Alphabet:** eigene Glyphen in quadratischen Zellen, an die Wiener Secession angelehnt. Strichstärke 16 (von 100), keine Ornament-Punkte, keine Rotation. Definiert in `design/canvas/Txt.dc.html` (Tabelle `G`: `[viewBox-x, Breite, Pfad]`, Breiten über die tatsächliche Tinte gemessen). Abstand zwischen Buchstaben 0,2 × Höhe. Nur Großbuchstaben, Umlaute werden zu AE/OE/UE.
- **WAISS diagonal (Luma-Cover):** Die Buchstabenmitten liegen exakt auf der 45°-Diagonale von Ecke zu Ecke. Bei 1080 × 1080 ist der Schritt 190 px (1 em bei 190 px), das I sitzt genau in der Bildmitte (540, 540). Jede Zeile ist 1 em hoch, damit der Zeilenabstand die Diagonale nicht verschiebt.
- **WAISS einzeilig:** Titelfolie.
- **Mono-Text:** IBM Plex Mono für Kleingedrucktes.

## Telos Circle

`assets/logo/`:
- `telos-circle.svg`: Säule allein, aus dem SVG von teloscircle.com bereinigt
- `telos-circle-wortmarke.svg`: Säule + „Telos *Circle*“ (Charis SIL, „Circle“ kursiv), Maße wie im Header der Webseite
- `telos-circle-by.svg`: „by“ + Wortmarke, steht auf dem Luma-Cover oben rechts unter „STAMMTISCH“

Die Schrift ist in Pfade umgewandelt, damit nichts nachgeladen werden muss.

## Blob

Ein nicht-newtonsches, metaball-artiges Objekt, angelehnt an einen 70er-Jahre-Sessel aus verschmolzenen Kugeln. Die Stacheln stehen für das „jagged frontier“-Meme der KI.

- WebGL-Raymarching (`design/canvas/Blob.dc.html`): 8 Metaballs mit Smooth-Union, leichtes Warping
- 14 Stacheln, Fibonacci-verteilt, weich mit dem Körper verschmolzen. Stacheln, die zur Kamera zeigen, ziehen sich ein (sonst sehen sie aus wie Nippel). Spitzen dunkler.
- Glanz über Studio-Umgebungsreflexion, Fresnel
- Parameter: `variant` (0–3), `zoom`, `shift-x`, `shift-y`, `rot-offset` (Grad), `spiky` (0,8), `shine` (0,8)
- Luma-Cover: Variante 2, Zoom 1,47, shift 0,075 / −0,15, Rotation −90°
- In der Präsentation steht er im Hintergrund und bewegt sich beim Folienwechsel organisch. Er ist nicht dauerhaft animiert.

## Formate

| Datei | Format | Status |
|---|---|---|
| `Luma.dc.html` | 1080 × 1080 | **Hauptflyer** (Luma-Cover) |
| `FlyerA.dc.html` | 1080 × 1350 | Hochformat, vorerst pausiert |
| `Main.dc.html` | 1920 × 1080 | Titelfolie |
| `Folien.dc.html` | 1920 × 1080 | Folien-Prototyp mit Blob-Übergängen |
| `Steuerpult.dc.html` | – | steuert Schrift und Rotation für alle Formate gleichzeitig (Experiment) |
| `Schriften.dc.html`, `Wortmarke.dc.html` | – | verworfene Schrift- und Wortmarken-Entwürfe, als Referenz |
