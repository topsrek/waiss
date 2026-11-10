// Export the deck built by tools/deck.py:
//   node tools/export-deck.js [build/deck] [exports/deck]
// -> one PNG per slide (the real deck, jumped to slide N) + waiss-slides.pdf (static fallback, ?print layout).
// Playwright's Chromium; the blob is WebGL, the swiftshader flags make it render without a GPU.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const [src = 'build/deck', dst = 'exports/deck'] = process.argv.slice(2);
  const { slides } = JSON.parse(fs.readFileSync(path.join(src, 'meta.json'), 'utf8'));
  const url = 'file://' + path.resolve(src, 'index.html');
  fs.mkdirSync(dst, { recursive: true });
  for (const f of fs.readdirSync(dst)) if (f.endsWith('.png')) fs.unlinkSync(path.join(dst, f)); // no stale slides
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  // Each load compiles the shader in SwiftShader (CPU) and fetches Google Fonts: on a busy CI runner that can take
  // longer than Playwright's default 30 s, so wait longer and try once more before giving up.
  const open = async (suffix, tries = 2) => {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
    page.on('console', (m) => m.type() === 'warning' || m.type() === 'error' ? console.warn(m.text()) : 0);
    try {
      await page.goto(url + suffix, { timeout: 120000 });
      await page.waitForFunction(() => document.documentElement.dataset.ready === '1', null, { timeout: 300000 });
    } catch (e) {
      await page.close();
      if (tries <= 1) throw e;
      console.warn(`retrying ${suffix}: ${e.message.split('\n')[0]}`);
      return open(suffix, tries - 1);
    }
    await page.waitForTimeout(1200); // slide fade-in (0.45 s delay + 0.55 s)
    return page;
  };
  // SwiftShader can lose the very first WebGL context while it compiles the shader: warm it up once.
  await (await open('#1')).close();
  for (let i = 0; i < slides.length; i++) {
    const page = await open('#' + (i + 1));
    const file = path.join(dst, slides[i] + '.png');
    await page.screenshot({ path: file });
    console.log('wrote', file);
    await page.close();
  }
  const page = await open('?print');
  const pdf = path.join(dst, 'waiss-slides.pdf');
  await page.pdf({ path: pdf, width: '1920px', height: '1080px', printBackground: true, preferCSSPageSize: true });
  console.log('wrote', pdf);
  await browser.close();
})();
