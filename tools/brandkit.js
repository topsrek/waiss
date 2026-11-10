// Render helper for tools/brandkit.py (run that one, not this file):
//   node tools/brandkit.js build/brandkit/job.json
// job.json: {fs, size, out, views: [{name, preset: [ph, rot, b], rot, zoom}], svgs: [{name, svg, width}]}
// -> <out>/<name>.png per view (size², transparent, the blob from the deck shader)
//    and per svg (rasterised at `width` px, transparent).
// SwiftShader like export-deck.js: no GPU needed, same pixels on every machine.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: 4000, height: 1600 } });
  page.on('console', (m) => m.type() === 'error' ? console.warn(m.text()) : 0);
  // SwiftShader loses the first WebGL context of a browser ~0.1 s after creating it; later draws then do nothing
  // and every image is the same. Spend a throwaway context on that first.
  await page.evaluate(() => new Promise((done) => {
    const c = document.createElement('canvas');
    c.addEventListener('webglcontextlost', done);
    c.getContext('webgl');
    setTimeout(done, 3000);
  }));
  const pngs = await page.evaluate((job) => {
    const c = document.createElement('canvas'); c.width = c.height = job.size;
    const gl = c.getContext('webgl', { alpha: true, premultipliedAlpha: true, preserveDrawingBuffer: true });
    const mk = (t, s) => { const sh = gl.createShader(t); gl.shaderSource(sh, s); gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(sh)); return sh; };
    const p = gl.createProgram();
    gl.attachShader(p, mk(gl.VERTEX_SHADER, 'attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}'));
    gl.attachShader(p, mk(gl.FRAGMENT_SHADER, job.fs)); gl.linkProgram(p); gl.useProgram(p);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const l = gl.getAttribLocation(p, 'a'); gl.enableVertexAttribArray(l); gl.vertexAttribPointer(l, 2, gl.FLOAT, false, 0, 0);
    const U = (n) => gl.getUniformLocation(p, n);
    gl.viewport(0, 0, job.size, job.size);
    return job.views.map((v) => {
      const [ph, rot, b] = v.preset;
      gl.uniform2f(U('uRes'), job.size, job.size); gl.uniform4fv(U('uB[0]'), new Float32Array(b));
      gl.uniform1f(U('uWarp'), 0.05); gl.uniform1f(U('uPhase'), ph); gl.uniform1f(U('uRot'), rot + v.rot * Math.PI / 180);
      gl.uniform3f(U('uCam'), v.zoom, 0, 0); gl.uniform1f(U('uShine'), 0.8); gl.uniform1f(U('uSpike'), 0.8);
      gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT); gl.drawArrays(gl.TRIANGLES, 0, 3);
      if (gl.isContextLost()) throw new Error('WebGL context lost while drawing ' + v.name);
      return c.toDataURL('image/png');
    });
  }, job);
  fs.mkdirSync(job.out, { recursive: true });
  job.views.forEach((v, i) => fs.writeFileSync(path.join(job.out, v.name + '.png'), Buffer.from(pngs[i].split(',')[1], 'base64')));
  for (const s of job.svgs || []) {
    await page.setContent(`<style>html,body{margin:0;background:transparent}svg{display:block;width:${s.width}px;height:auto}</style>${s.svg}`);
    await page.locator('svg').screenshot({ path: path.join(job.out, s.name + '.png'), omitBackground: true });
  }
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
