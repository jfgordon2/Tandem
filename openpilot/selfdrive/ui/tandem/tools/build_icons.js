#!/usr/bin/env node
// Rasterizes the line icons in ../icons/svg (copied from the design mocks) to white PNGs in ../icons.
// The UI tints the PNGs when it draws them, so each is white on transparent. Needs Playwright's
// Chromium only to regenerate the PNGs, not on the device. Run: node tools/build_icons.js
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const ICON_DIR = path.resolve(__dirname, '..', 'icons');
const SIZE = 128;   // big enough for the largest use (a 54 px glyph at 1.92x); smaller sizes are scaled down on load

(async () => {
  const sources = fs.readdirSync(path.join(ICON_DIR, 'svg')).filter((f) => f.endsWith('.svg')).sort();
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: SIZE, height: SIZE } });
  for (const file of sources) {
    const markup = fs.readFileSync(path.join(ICON_DIR, 'svg', file), 'utf8').replace('<svg ', `<svg width="${SIZE}" height="${SIZE}" `);
    await page.setContent(`<html><body style="margin:0;background:transparent">${markup}</body></html>`);
    await page.locator('svg').screenshot({ path: path.join(ICON_DIR, file.replace('.svg', '.png')), omitBackground: true });
  }
  await browser.close();
  console.log(`wrote ${sources.length} icons to ${ICON_DIR}`);
})();
