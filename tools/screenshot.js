// Screenshot every page built by render.py.
//   node tools/screenshot.js build/001 exports/001 [scale]
// Uses Playwright's Chromium. The blob is WebGL; on machines without a GPU the
// swiftshader flags below make it render in software.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
  const [src, dst, scale = '1'] = process.argv.slice(2);
  if (!src || !dst) { console.error('usage: node tools/screenshot.js <build dir> <out dir> [scale]'); process.exit(1); }
  const sizes = JSON.parse(fs.readFileSync(path.join(src, 'sizes.json'), 'utf8'));
  fs.mkdirSync(dst, { recursive: true });
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  for (const [name, [width, height]] of Object.entries(sizes)) {
    const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: +scale });
    await page.goto('file://' + path.resolve(src, name + '.html'));
    await page.waitForFunction(() => document.title === 'ready', null, { timeout: 60000 });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(500);
    const file = path.join(dst, `${name}${scale === '1' ? '' : '@' + scale + 'x'}.png`);
    await page.screenshot({ path: file });
    console.log('wrote', file);
    await page.close();
  }
  await browser.close();
})();
