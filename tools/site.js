document.documentElement.classList.add('js');

/* ---- upcoming vs. past, decided by today's date in Vienna: an edition is past from the day after it ---- */
(() => {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Vienna', year: 'numeric', month: '2-digit', day: '2-digit' })
    .format(new Date());
  const up = document.getElementById('up'), past = document.getElementById('past');
  if (!up || !past) return;
  const rows = [...document.querySelectorAll('.ed-row')];
  rows.filter(r => r.dataset.day >= today).sort((a, b) => a.dataset.day.localeCompare(b.dataset.day)).forEach(r => up.append(r));
  rows.filter(r => r.dataset.day < today).sort((a, b) => b.dataset.day.localeCompare(a.dataset.day)).forEach(r => past.append(r));
  for (const r of rows) {
    const isPast = r.dataset.day < today;
    r.querySelectorAll('[data-upcoming]').forEach(e => { e.hidden = isPast; });
    r.querySelectorAll('[data-past]').forEach(e => { e.hidden = !isPast; });
    r.querySelectorAll('[data-today]').forEach(e => { e.hidden = r.dataset.day !== today; });
  }
  document.querySelectorAll('[data-until]').forEach(e => { e.hidden = e.dataset.until < today; });
  document.getElementById('up-empty').hidden = up.children.length > 0;
  document.getElementById('past-empty').hidden = past.children.length > 0;
  const next = [...document.querySelectorAll('.next[data-next]')].filter(c => c.dataset.next !== 'tba')
    .filter(c => c.dataset.next >= today).sort((a, b) => a.dataset.next.localeCompare(b.dataset.next))[0];
  document.querySelectorAll('.next[data-next]').forEach(c => {
    c.hidden = next ? c !== next : c.dataset.next !== 'tba';
    const w = c.querySelector('[data-when]');
    if (w) w.textContent = c.dataset.next === today ? 'Tonight' : 'Next';
  });
})();

/* ---- slides: one tab per edition ---- */
(() => {
  const tabs = [...document.querySelectorAll('[data-tab]')];
  const show = id => tabs.forEach(t => {
    const on = t.dataset.tab === id;
    t.setAttribute('aria-selected', on);
    document.getElementById(t.dataset.tab).toggleAttribute('data-off', !on);
  });
  tabs.forEach(t => t.addEventListener('click', () => show(t.dataset.tab)));
  const fromHash = () => { const id = location.hash.slice(1); if (tabs.some(t => t.dataset.tab === id)) show(id); };
  addEventListener('hashchange', fromHash);
  fromHash();
})();

/* ---- the blob: same shader as the slides; it turns and travels when a new section reaches the middle ---- */
(() => {
  const cv = document.getElementById('blob');
  const data = JSON.parse(document.getElementById('blob-data').textContent);
  let gl = null, u = null;
  const init = () => {
    gl = cv.getContext('webgl', { alpha: true, premultipliedAlpha: true, antialias: false });
    if (!gl) return false;
    const mk = (t, s) => { const sh = gl.createShader(t); gl.shaderSource(sh, s); gl.compileShader(sh); return sh; };
    const p = gl.createProgram();
    gl.attachShader(p, mk(gl.VERTEX_SHADER, 'attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}'));
    gl.attachShader(p, mk(gl.FRAGMENT_SHADER, data.fs));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS) && !gl.isContextLost()) return false;
    gl.useProgram(p);
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(p, 'a'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const U = n => gl.getUniformLocation(p, n);
    u = { res: U('uRes'), b: U('uB[0]'), warp: U('uWarp'), ph: U('uPhase'), rot: U('uRot'), cam: U('uCam'), shine: U('uShine'), spike: U('uSpike') };
    return true;
  };
  if (!init()) return;
  // a lost context paints the canvas white: hide it, and draw again once the browser gives it back
  cv.addEventListener('webglcontextlost', e => { e.preventDefault(); cancelAnimationFrame(raf); cv.style.visibility = 'hidden'; });
  cv.addEventListener('webglcontextrestored', () => { if (init() && cur) { draw(cur, quality()); cv.style.visibility = ''; } });
  const [ph0, rot0, b0] = data.presets[data.variant];

  const draw = (s, q) => {
    if (gl.isContextLost()) return;
    const w = Math.max(1, Math.round(innerWidth * q)), h = Math.max(1, Math.round(innerHeight * q));
    if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
    gl.viewport(0, 0, w, h); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(u.res, w, h); gl.uniform4fv(u.b, new Float32Array(b0));
    gl.uniform1f(u.warp, 0.05); gl.uniform1f(u.ph, ph0); gl.uniform1f(u.rot, s.rot);
    gl.uniform3f(u.cam, s.cam[0], s.cam[1], s.cam[2]); gl.uniform1f(u.shine, 0.8); gl.uniform1f(u.spike, 0.8);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };
  // render budget: about 1.6 MP when resting, half of that while moving
  const quality = () => Math.max(.4, Math.min(devicePixelRatio || 1, 1.5, Math.sqrt(1.6e6 / (innerWidth * innerHeight))));
  const narrow = () => innerWidth / innerHeight < 1.1;
  const goalOf = el => {
    const [z, sx, sy, r] = (narrow() && el.dataset.camM ? el.dataset.camM : el.dataset.cam).split(',').map(Number);
    return { rot: rot0 + r * Math.PI / 180, cam: [z, sx, sy] };
  };
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let cur = null, active = null, raf = 0;

  const go = el => {
    if (el === active) return;
    active = el;
    const goal = goalOf(el);
    if (!cur || reduce) { cur = goal; draw(cur, quality()); return; }
    const d = goal.rot - cur.rot; goal.rot = cur.rot + Math.atan2(Math.sin(d), Math.cos(d));
    const from = cur, t0 = performance.now(), dur = 1100, lerp = (a, b, e) => a + (b - a) * e;
    cancelAnimationFrame(raf);
    const step = now => {
      const k = Math.min(1, (now - t0) / dur), e = k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      cur = { rot: lerp(from.rot, goal.rot, e), cam: from.cam.map((v, i) => lerp(v, goal.cam[i], e)) };
      draw(cur, k < 1 ? quality() * .5 : quality());
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
  };

  const stops = [...document.querySelectorAll('[data-cam]')];
  const pick = () => {
    const mid = innerHeight * .5;
    let best = stops[0];
    for (const s of stops) if (s.getBoundingClientRect().top <= mid) best = s;
    go(best);
  };
  let ticking = false;
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(() => { ticking = false; pick(); }); } }, { passive: true });
  let rz = 0;
  addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => { if (active) { cur = goalOf(active); draw(cur, quality()); } }, 150); });
  pick();
})();
