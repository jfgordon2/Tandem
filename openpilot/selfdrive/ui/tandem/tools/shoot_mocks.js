#!/usr/bin/env node
// Screenshots the design mocks into ../design/screenshots/<name>.png, one per mock's root <div>.
// Run: node tools/shoot_mocks.js [name ...]   (no names: every design/*.html). Needs Playwright's Chromium.
// It also lists any element whose content overflows a clipped box, so cramped mocks show up.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const DESIGN = path.resolve(__dirname, '..', 'design');

(async () => {
  const names = process.argv.slice(2).length ? process.argv.slice(2)
    : fs.readdirSync(DESIGN).filter((f) => f.endsWith('.html')).map((f) => f.replace(/\.html$/, '')).sort();
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1600, height: 1600 } });
  for (const name of names) {
    await page.goto('file://' + path.join(DESIGN, name + '.html'));
    await page.waitForTimeout(300);   // web fonts
    const root = await page.$('body > div');
    const clipped = await page.evaluate(() => {
      const out = [];
      document.querySelectorAll('body > div *').forEach((e) => {
        if (e.scrollHeight > e.clientHeight + 2 && getComputedStyle(e).overflow === 'hidden') out.push(e.tagName);
      });
      return out.slice(0, 5);
    });
    await root.screenshot({ path: path.join(DESIGN, 'screenshots', name + '.png') });
    console.log(name + (clipped.length ? '  clipped: ' + clipped.join(', ') : ''));
  }
  await browser.close();
})();
