document.documentElement.classList.add('js');
document.querySelectorAll('[data-mail]').forEach(a => {
  const [u, d] = a.dataset.mail.split('|'); a.href = 'mailto:' + u + '@' + d; a.textContent = u + '@' + d;
});

/* ---- editions: state per card from today's date in Vienna; an edition is past from the day after it ---- */
(() => {
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Vienna', year: 'numeric', month: '2-digit', day: '2-digit' })
    .format(new Date());
  const cards = [...document.querySelectorAll('.ed[data-day]')];
  for (const c of cards) {
    const st = c.dataset.day < today ? 'past' : c.dataset.day === today ? 'today' : 'upcoming';
    c.dataset.state = st;
    c.querySelector('[data-st]').textContent = st[0].toUpperCase() + st.slice(1);
    c.querySelectorAll('[data-upcoming]').forEach(e => { e.hidden = st === 'past'; });
    c.querySelectorAll('[data-past]').forEach(e => { e.hidden = st !== 'past'; });
  }
  const tba = document.querySelector('[data-tba]');
  if (tba) tba.hidden = cards.some(c => c.dataset.day > today);
  // upcoming first (soonest on top), then "Past" and the past ones (most recent on top); the page may be older than today
  const list = document.getElementById('eds'), sep = document.querySelector('[data-sep]');
  if (list && sep) {
    const by = (a, b) => a.dataset.day.localeCompare(b.dataset.day);
    const past = cards.filter(c => c.dataset.state === 'past').sort(by).reverse();
    list.append(...cards.filter(c => c.dataset.state !== 'past').sort(by), ...(tba ? [tba] : []), sep, ...past);
    sep.hidden = !past.length;
  }
  document.querySelectorAll('[data-until]').forEach(e => { e.hidden = e.dataset.until < today; });
})();

/* ---- the blob: same shader as the slides; it turns and travels when a new section reaches the middle ----
   The shader draws only a square around the blob. Where that square sits and how big it is is a CSS transform, so
   travelling and zooming cost the GPU nothing; only the turn needs new frames. Once the blob rests, the sharp frame
   is drawn offscreen a few strips per animation frame and shown when complete, so no single frame is expensive.
   A fast GPU draws the turn live, at reduced size. On a slow one (a phone: ~70 ms for 512² px) the turn plays from a
   cache instead: a frame every 6°, drawn in strips while nothing else is drawing, nearest angles first; a turn mixes
   the two cached frames around its angle. The cache lives in main memory and only the two frames in use are on the
   GPU: 60 textures there made Chrome on Android drop every frame of the first scroll. A turn the cache can't play
   yet only travels and then fades.
   The shader compiles in the background (KHR_parallel_shader_compile) after the first paint, so the page never
   waits for it; the canvas fades in once the first frame is drawn. */
(() => {
  const cv = document.getElementById('blob');
  const data = JSON.parse(document.getElementById('blob-data').textContent);
  const R = 0.7;                  // half the square, in the shader's image units (the blob reaches 0.65 at any angle)
  const BASE = 1000;              // CSS size of the canvas before its transform
  const CAP = 1.4e6;              // sharp frame: at most 1.4 MP
  const K = 60, STEP = 2 * Math.PI / K;  // turn cache: 60 frames, 6° apart
  const frame = () => new Promise(r => requestAnimationFrame(r));
  const [ph0, rot0, b0] = data.presets[data.variant];
  let gl = null, P = null, Q = null, ready = false, lo = null, hi = null, nx = null, cache = null, busy = false;

  const program = async (fs, vs = 'attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}') => {
    const par = gl.getExtension('KHR_parallel_shader_compile');
    const mk = (t, s) => { const sh = gl.createShader(t); gl.shaderSource(sh, s); gl.compileShader(sh); return sh; };
    const p = gl.createProgram();
    gl.attachShader(p, mk(gl.VERTEX_SHADER, vs)); gl.attachShader(p, mk(gl.FRAGMENT_SHADER, fs));
    gl.bindAttribLocation(p, 0, 'a'); gl.linkProgram(p);
    if (par) while (!gl.getProgramParameter(p, par.COMPLETION_STATUS_KHR) && !gl.isContextLost()) await frame();
    return gl.getProgramParameter(p, gl.LINK_STATUS) ? p : null;
  };
  const init = async () => {
    gl = cv.getContext('webgl', { alpha: true, premultipliedAlpha: true, antialias: false });
    if (!gl) return false;
    lo = hi = nx = cache = null;
    [P, Q] = await Promise.all([program(data.fs), program(
      'precision mediump float;varying vec2 v;uniform sampler2D t,s;uniform float f;void main(){gl_FragColor=mix(texture2D(s,v),texture2D(t,v),f);}',
      'attribute vec2 a;varying vec2 v;void main(){v=a*.5+.5;gl_Position=vec4(a,0.,1.);}')]);
    if (!P || !Q) return false;
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.useProgram(P);
    const U = n => gl.getUniformLocation(P, n);
    gl.uniform4fv(U('uB[0]'), new Float32Array(b0)); gl.uniform1f(U('uWarp'), 0.05); gl.uniform1f(U('uPhase'), ph0);
    gl.uniform3f(U('uCam'), 1 / (2 * R), 0, 0); gl.uniform1f(U('uShine'), 0.8); gl.uniform1f(U('uSpike'), data.spike);
    gl.uniform3fv(U('gDir[0]'), new Float32Array(data.dirs)); gl.uniform4fv(U('gTip[0]'), new Float32Array(data.tips));
    P.res = U('uRes'); P.rot = U('uRot');
    gl.useProgram(Q); gl.uniform1i(gl.getUniformLocation(Q, 's'), 1); Q.f = gl.getUniformLocation(Q, 'f');
    gl.clearColor(0, 0, 0, 0);
    return true;
  };

  // an offscreen square of n×n pixels for the shader to draw into; rot is the angle it holds once complete
  const target = (old, n) => {
    if (old && old.n === n) { old.rot = NaN; return old; }
    if (old) { gl.deleteTexture(old.t); gl.deleteFramebuffer(old.f); }
    const t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, n, n, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR],
                          [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
    const f = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, f);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
    return { t, f, n, rot: NaN };
  };
  const scene = (rot, tg, y0, y1) => {      // rows y0..y1 of the blob at angle rot
    gl.bindFramebuffer(gl.FRAMEBUFFER, tg.f); gl.viewport(0, 0, tg.n, tg.n);
    gl.enable(gl.SCISSOR_TEST); gl.scissor(0, y0, tg.n, y1 - y0);
    gl.useProgram(P); gl.uniform2f(P.res, tg.n, tg.n); gl.uniform1f(P.rot, rot);
    gl.clear(gl.COLOR_BUFFER_BIT); gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.disable(gl.SCISSOR_TEST);
  };
  const show = (tg, size = hi ? cv.width : tg.n, old = tg, f = 1) => {  // a square onto the canvas, stretched; f < 1 mixes in old
    if (cv.width !== size || cv.height !== size) cv.width = cv.height = size;
    gl.bindFramebuffer(gl.FRAMEBUFFER, null); gl.viewport(0, 0, size, size);
    gl.useProgram(Q); gl.uniform1f(Q.f, f);
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, old.t);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, tg.t);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    cv.classList.add('on');
  };

  // the shader's camera (zoom, shift x, shift y in screen heights) as a CSS transform of the square
  const side = cam => 2 * R * cam[0] * innerHeight;          // CSS px
  const place = cam => {
    const H = innerHeight, s = side(cam);
    cv.style.transform = `translate3d(${innerWidth / 2 + cam[1] * H - s / 2}px,${H / 2 - cam[2] * H - s / 2}px,0) scale(${s / BASE})`;
  };
  const sharp = cam => Math.round(Math.max(64, Math.min(side(cam) * Math.min(devicePixelRatio || 1, 1.5), Math.sqrt(CAP))));
  let soft = 0.5;                 // size of the frames drawn live while turning, relative to the sharp one

  const narrow = () => innerWidth / innerHeight < 1.1;
  const goalOf = el => {
    const [z, sx, sy, r] = (narrow() && el.dataset.camM ? el.dataset.camM : el.dataset.cam).split(',').map(Number);
    return { rot: rot0 + r * Math.PI / 180, cam: [z, sx, sy] };
  };
  const stops = [...document.querySelectorAll('[data-cam]')];
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let cur = null, active = null, raf = 0;

  // How fast this GPU draws the blob, in ms per pixel: one small square, drawn and waited for. Sets how big a frame
  // may be while turning live (about 6 ms) and how many rows go into one animation frame (about 8 ms).
  let fast = 600, strip = 3e5;
  const probe = () => {
    const n = 256, t = target(null, n), px = new Uint8Array(4);
    scene(rot0, t, 0, 4); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);   // the first draw may still compile
    const t0 = performance.now();
    scene(rot0, t, 0, n); gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    const c = Math.max(performance.now() - t0, 0.1) / (n * n);
    gl.deleteTexture(t.t); gl.deleteFramebuffer(t.f);
    fast = Math.sqrt(6 / c); strip = Math.max(5e3, Math.min(6e5, 8 / c));
  };

  // the turn cache: frame k shows the blob at angle k·STEP
  const slot = rot => {
    const x = ((rot % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI) / STEP, i = Math.floor(x);
    return [i % K, (i + 1) % K, x - i];
  };
  const startCache = () => {
    const big = Math.max(...stops.map(s => sharp(goalOf(s).cam))), n = Math.round(Math.max(96, Math.min(256, 0.5 * big)));
    const slot = () => { const t = target(null, n); gl.deleteFramebuffer(t.f); t.k = -1; return t; };
    // f[k].px: frame k once complete; tg: where it is drawn; at: the frame being drawn; up: the two frames on the GPU
    cache = { n, f: Array.from({ length: K }, () => ({ px: null, y: 0 })), tg: target(null, n), at: -1, up: [slot(), slot()] };
    requestAnimationFrame(fill);
  };
  const upload = (k, keep) => {             // frame k into a GPU slot not holding frame keep
    let s = cache.up.find(s => s.k === k);
    if (!s) {
      s = cache.up.find(s => s.k !== keep); s.k = k;
      gl.bindTexture(gl.TEXTURE_2D, s.t);
      gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, cache.n, cache.n, gl.RGBA, gl.UNSIGNED_BYTE, cache.f[k].px);
    }
    return s;
  };
  const cached = (a, b) => {                // can the cache play the turn from angle a to angle b?
    if (!cache) return false;
    const i0 = slot(Math.min(a, b))[0], n = Math.ceil(Math.abs(b - a) / STEP) + 2;
    for (let k = 0; k < n; k++) if (!cache.f[(i0 + k) % K].px) return false;
    return true;
  };
  const fill = () => {                      // a strip of the missing frame nearest to the blob's angle
    if (!cache || !ready || gl.isContextLost()) return;
    if (cache.at < 0) {
      const c0 = slot(cur ? cur.rot : rot0)[0];
      for (let d = 0; d <= K / 2 && cache.at < 0; d++) for (const k of [(c0 + d) % K, (c0 - d + K) % K]) if (!cache.f[k].px) { cache.at = k; break; }
      if (cache.at < 0) { gl.deleteTexture(cache.tg.t); gl.deleteFramebuffer(cache.tg.f); return; }  // complete
    }
    requestAnimationFrame(fill);
    if (busy) return;                       // a turn or a sharp frame is drawing: that first
    const k = cache.at, f = cache.f[k], n = cache.n, rows = Math.max(8, Math.floor(strip / n));
    scene(k * STEP, cache.tg, f.y, Math.min(n, f.y + rows));
    if ((f.y += rows) < n) return;
    const px = new Uint8Array(n * n * 4);
    gl.readPixels(0, 0, n, n, gl.RGBA, gl.UNSIGNED_BYTE, px);
    f.px = px; cache.at = -1;
  };

  // The sharp frame at angle rot, drawn offscreen in strips while the canvas keeps showing what it shows. If the blob
  // on screen is at another angle (a turn that only travelled), the old picture fades into the new one.
  const settle = (rot = cur && cur.rot) => {
    cancelAnimationFrame(raf);
    busy = false;
    if (!ready || !cur || gl.isContextLost()) return;
    const n = sharp(cur.cam);
    if (hi && hi.rot === rot && Math.abs(hi.n - n) < 0.15 * n) { show(hi, hi.n); cur.rot = rot; return; }
    busy = true;
    nx = target(nx, n);
    const rows = Math.max(8, Math.floor(strip / n));
    let y = 0;
    const step = () => {
      if (gl.isContextLost()) return;
      scene(rot, nx, y, Math.min(n, y + rows)); y += rows;
      if (y < n) { raf = requestAnimationFrame(step); return; }
      nx.rot = rot;
      const old = rot !== cur.rot && hi && hi.rot === cur.rot ? hi : null;
      cur.rot = rot; [hi, nx] = [nx, hi];
      if (!old) { show(hi, n); busy = false; return; }
      const t0 = performance.now();
      const fade = now => {
        const f = Math.min(1, (now - t0) / 500);
        show(hi, n, old, f * f * (3 - 2 * f));
        if (f < 1) raf = requestAnimationFrame(fade); else busy = false;
      };
      fade(t0);
    };
    step();
  };

  const go = el => {
    if (el === active) return;
    active = el;
    const goal = goalOf(el);
    if (!cur || reduce || !ready) { cur = goal; place(cur.cam); settle(); return; }
    const d = goal.rot - cur.rot; goal.rot = cur.rot + Math.atan2(Math.sin(d), Math.cos(d));
    const from = cur, t0 = performance.now(), dur = 1100, lerp = (a, b, e) => a + (b - a) * e;
    const big = Math.max(sharp(from.cam), sharp(goal.cam)), m = Math.round(Math.min(soft * big, fast));
    const turn = Math.abs(goal.rot - from.rot) > 1e-4;
    const live = turn && !cache && m >= 0.3 * big;                 // this GPU draws the turn
    const play = turn && !live && cached(from.rot, goal.rot);      // the cache has it
    if (live) lo = target(lo, m);
    let last = t0, slow = 0, frames = 0;
    cancelAnimationFrame(raf);
    busy = true;
    const step = now => {
      const k = Math.min(1, (now - t0) / dur), e = k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      cur = k < 1 ? { rot: live || play ? lerp(from.rot, goal.rot, e) : from.rot, cam: from.cam.map((v, i) => lerp(v, goal.cam[i], e)) }
                  : { rot: live || play ? goal.rot : from.rot, cam: goal.cam };
      place(cur.cam);
      if (k < 1 && !gl.isContextLost()) {
        if (live) { scene(cur.rot, lo, 0, m); show(lo); frames++; if (now - last > 24) slow++; }
        else if (play) { const [i, j, f] = slot(cur.rot); show(upload(j, i), undefined, upload(i, j), f); }
      }
      last = now;
      if (k < 1) { raf = requestAnimationFrame(step); return; }
      if (frames > 10 && slow > frames / 4) {                        // the GPU could not keep up
        soft *= 0.75;
        if (soft < 0.3 && !cache) startCache();
      }
      settle(goal.rot);
    };
    raf = requestAnimationFrame(step);
  };

  const pick = () => {
    const mid = innerHeight * .5;
    let best = stops[0];
    for (const s of stops) if (s.getBoundingClientRect().top <= mid) best = s;
    go(best);
  };
  const start = async () => {
    ready = await init();
    if (!ready) return;
    probe();
    cur = null; active = null; pick();
    if (fast < 0.5 * Math.max(...stops.map(s => sharp(goalOf(s).cam)))) startCache();
  };
  // a lost context paints the canvas white: hide it, and draw again once the browser gives it back
  cv.addEventListener('webglcontextlost', e => { e.preventDefault(); cancelAnimationFrame(raf); ready = false; cv.classList.remove('on'); });
  cv.addEventListener('webglcontextrestored', start);
  let ticking = false;
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(() => { ticking = false; pick(); }); } }, { passive: true });
  let rz = 0;
  addEventListener('resize', () => {
    clearTimeout(rz);
    rz = setTimeout(() => { if (active) { cancelAnimationFrame(raf); cur = goalOf(active); place(cur.cam); settle(); } }, 150);
  });
  pick();                                  // places the blob for the section in view; draws once the shader is ready
  frame().then(frame).then(start);         // after the first paint
})();
