#!/usr/bin/env python3
"""Build static, self-contained HTML pages from the design canvas sources.

    python3 tools/render.py editions/001.json        # -> build/001/*.html
    node tools/screenshot.js build/001 exports/001   # -> PNGs

The *.dc.html files in design/canvas/ are the source of truth (they come from the
Claude design canvas and use its template syntax: {{holes}}, <dc-import>, data-props).
This script resolves that syntax without the canvas runtime:
  * <dc-import name="Txt">  -> inline SVG glyphs of the Secession alphabet (Txt.dc.html)
  * <dc-import name="Blob"> -> <canvas> + the WebGL fragment shader from Blob.dc.html
  * {{holes}}               -> values from DEFAULTS, overridden by the edition JSON
"""
import json, re, sys, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "design" / "canvas"
INK = "#1F1E1B"

# --- Blob shader + presets -------------------------------------------------------
blob_src = (SRC / "Blob.dc.html").read_text()
FS = re.search(r"const fs = `(.*?)`;", blob_src, re.S).group(1)
PRESET_RE = r"\{ ph: ([\d.]+), rot: ([\d.]+), b: \[(.*?)\] \}"
PRESETS = [(float(m.group(1)), float(m.group(2)), json.loads("[" + m.group(3) + "]"))
           for m in re.finditer(PRESET_RE, blob_src)]

# --- Secession glyphs ------------------------------------------------------------
G = json.loads(re.search(r"const G = (\{.*?\});", (SRC / "Txt.dc.html").read_text()).group(1))


def txt(text, size):
    raw = str(text).upper().replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE").replace("ß", "SS")
    raw = "".join(c for c in unicodedata.normalize("NFD", raw) if unicodedata.category(c) != "Mn")
    h = float(size)
    out = ""
    for ch in raw:
        x, w, d = G.get(ch, G[" "])
        out += (f'<svg viewBox="{x} 0 {w} 100" style="display:block;flex:none;width:{w / 100 * h:.1f}px;'
                f'height:{h}px;overflow:visible"><path d="{d or "M0,0"}" fill="none" stroke="{INK}" '
                f'stroke-width="16" stroke-linejoin="miter"/></svg>')
    return f'<div style="display:flex;align-items:flex-end;gap:{0.2 * h:.1f}px;height:{h}px">{out}</div>'


# Values the canvas computes in renderVals() for the default settings (Tektur, no rotation).
DEFAULTS = {
    "ff": "'Tektur', sans-serif", "fs": "normal", "fw": "800", "fv": "normal", "hb": "none",
    "hclip": "border-box", "hcol": INK, "hst": "0px transparent", "sk": "skewX(0deg)",
    "cw": "auto", "ls": "0em", "lh": "0.84",
    # Luma cover blob (option 7)
    "bVar": 2, "bZoom": 1.47, "bX": 0.075, "bY": -0.15, "bRot": -90,
}
for i in range(1, 6):
    DEFAULTS[f"l{i}t"] = "rotateZ(0deg) scaleY(1)"
    DEFAULTS[f"l{i}v"] = "normal"

BOARDS = [  # source file, output name, width, height, extra values
    ("Luma.dc.html", "luma-cover", 1080, 1080, {}),
    ("FlyerA.dc.html", "flyer-a", 1080, 1350, {}),
    ("Main.dc.html", "titelfolie", 1920, 1080, {}),
    ("Folien.dc.html", "folie-agenda", 1920, 1080, {"v": 0, "z": 1.1, "sx": 0.62, "sy": 0.0, "counter": "01 / 04"}),
]


def blob_script():
    return f"""<script>
const PRESETS={json.dumps(PRESETS)};const FS=`{FS}`;
document.querySelectorAll('canvas.blob').forEach(c=>{{
 const gl=c.getContext('webgl',{{premultipliedAlpha:true,alpha:true,preserveDrawingBuffer:true}});
 const mk=(t,s)=>{{const sh=gl.createShader(t);gl.shaderSource(sh,s);gl.compileShader(sh);
   if(!gl.getShaderParameter(sh,gl.COMPILE_STATUS))console.error(gl.getShaderInfoLog(sh));return sh;}};
 const p=gl.createProgram();
 gl.attachShader(p,mk(gl.VERTEX_SHADER,'attribute vec2 a;void main(){{gl_Position=vec4(a,0.,1.);}}'));
 gl.attachShader(p,mk(gl.FRAGMENT_SHADER,FS));gl.linkProgram(p);gl.useProgram(p);
 gl.bindBuffer(gl.ARRAY_BUFFER,gl.createBuffer());
 gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]),gl.STATIC_DRAW);
 const l=gl.getAttribLocation(p,'a');gl.enableVertexAttribArray(l);gl.vertexAttribPointer(l,2,gl.FLOAT,false,0,0);
 const U=n=>gl.getUniformLocation(p,n);const [ph,rot,b]=PRESETS[(+c.dataset.v)%PRESETS.length];
 gl.uniform2f(U('uRes'),c.width,c.height);gl.uniform4fv(U('uB[0]'),new Float32Array(b));
 gl.uniform1f(U('uWarp'),0.05);gl.uniform1f(U('uPhase'),ph);gl.uniform1f(U('uRot'),rot+(+c.dataset.r)*Math.PI/180);
 gl.uniform3f(U('uCam'),+c.dataset.z,+c.dataset.sx,+c.dataset.sy);gl.uniform1f(U('uShine'),0.8);gl.uniform1f(U('uSpike'),0.8);
 gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.drawArrays(gl.TRIANGLES,0,3);}});
document.title='ready';
</script>"""


def render(fn, w, h, vals):
    s = (SRC / fn).read_text()
    head = "".join(re.findall(r"<link [^>]*>", s)) + "".join(re.findall(r"<style>.*?</style>", s, re.S))
    body = re.search(r"</helmet>(.*)</x-dc>", s, re.S).group(1)
    fill = lambda v: re.sub(r"\{\{\s*([\w.]+)\s*\}\}", lambda m: str(vals.get(m.group(1), m.group(0))), v)

    def imp(m):
        a = {k: fill(v) for k, v in re.findall(r'([\w-]+)="([^"]*)"', m.group(0))}
        if a["name"] == "Txt":
            return txt(a["text"], a["size"])
        if a["name"] == "Blob":
            return (f'<canvas class="blob" width="{a["w"]}" height="{a["h"]}" data-v="{a.get("variant", 0)}" '
                    f'data-z="{a.get("zoom", 0.8)}" data-sx="{a.get("shift-x", 0)}" data-sy="{a.get("shift-y", 0)}" '
                    f'data-r="{a.get("rot-offset", 0)}" style="width:{a["w"]}px;height:{a["h"]}px;display:block"></canvas>')
        return ""

    body = re.sub(r"<dc-import [^>]*></dc-import>", imp, body)
    body = re.sub(r'<sc-if[^>]*value="\{\{s0\}\}"[^>]*>(.*?)</sc-if>', r"\1", body, flags=re.S)
    body = re.sub(r"<sc-if[^>]*>.*?</sc-if>", "", body, flags=re.S)
    body = re.sub(r"\{\{\s*([\w.]+)\s*\}\}", lambda m: str(vals.get(m.group(1), "")), body)
    return (f'<!doctype html><html><head><meta charset="utf-8">{head}</head>'
            f'<body style="margin:0;width:{w}px;height:{h}px;overflow:hidden">{body}{blob_script()}</body></html>')


def main():
    edition_file = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "editions" / "001.json")
    ed = json.loads(edition_file.read_text())
    out = ROOT / "build" / edition_file.stem
    out.mkdir(parents=True, exist_ok=True)
    vals = dict(DEFAULTS)
    vals.update({
        "edition": ed["edition"],
        "datum": f'{ed["datum"]} · {ed["zeit"]}' if ed.get("zeit") else ed["datum"],
        "ort": ed["ort"],
    })
    sizes = {}
    for fn, name, w, h, extra in BOARDS:
        html = render(fn, w, h, {**vals, **extra})
        # The Flyer A footer is plain text in the source: swap in this edition's address + link.
        if fn == "FlyerA.dc.html":
            html = html.replace("Mariahilfer Str. 73 · luma.com/ba5jlhla",
                                f'{ed["adresse_kurz"]} · {ed["anmeldung"].replace("https://", "")}')
        (out / f"{name}.html").write_text(html)
        sizes[name] = [w, h]
    (out / "sizes.json").write_text(json.dumps(sizes))
    print(f"built {out}")


if __name__ == "__main__":
    main()
