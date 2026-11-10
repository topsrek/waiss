// Render the favicon PNGs (the Secession W from tools/site.py's favicon()) into assets/icons/.
//   node tools/icons.js        (npm run icons; only needed when the W or ICON_SPECS change)
// tools/site.py turns them into favicon.ico, apple-touch-icon.png and the web manifest icons.
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const py = `import importlib.util as u, json
s = u.spec_from_file_location("waiss_site", "tools/site.py"); m = u.module_from_spec(s); s.loader.exec_module(m)
print(json.dumps({n: [px, m.favicon(**a)] for n, (px, a) in m.ICON_SPECS.items()}))`;
const specs = JSON.parse(execFileSync(process.platform === 'win32' ? 'python' : 'python3', ['-X', 'utf8', '-c', py],
  { cwd: root, encoding: 'utf8' }));

(async () => {
  const dst = path.join(root, 'assets', 'icons');
  fs.mkdirSync(dst, { recursive: true });
  const browser = await chromium.launch();
  for (const [name, [px, svg]] of Object.entries(specs)) {
    const page = await browser.newPage({ viewport: { width: px, height: px } });
    await page.setContent(`<style>html,body{margin:0;background:transparent}svg{display:block;width:${px}px;height:${px}px}</style>${svg}`);
    const file = path.join(dst, name + '.png');
    await page.screenshot({ path: file, omitBackground: true });
    console.log('wrote', path.relative(root, file));
    await page.close();
  }
  await browser.close();
})();
