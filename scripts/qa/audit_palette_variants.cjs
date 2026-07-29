#!/usr/bin/env node
/* eslint-disable no-console */

const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');

const paletteDir = path.resolve(process.argv[2] || '');
if (!paletteDir || !fs.existsSync(paletteDir)) {
  throw new Error('Usage: audit_palette_variants.cjs <palette-preview-dir>');
}

const screenshotDir = path.join(paletteDir, 'screenshots');
fs.mkdirSync(screenshotDir, { recursive: true });

async function auditVariant(browser, file) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    serviceWorkers: 'block',
  });
  const page = await context.newPage();
  const consoleErrors = [];
  const failedRequests = [];
  const remoteRequests = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('requestfailed', (request) => failedRequests.push(request.url()));
  page.on('request', (request) => {
    if (/^https?:/i.test(request.url())) remoteRequests.push(request.url());
  });
  await page.goto(pathToFileURL(file).href, { waitUntil: 'load' });
  await page.waitForTimeout(150);
  const metrics = await page.evaluate(() => {
    const body = document.body;
    const style = getComputedStyle(body);
    const hero = document.querySelector('.designed-hero-composer');
    const html = document.documentElement;
    return {
      overflow_px: Math.max(body.scrollWidth, html.scrollWidth) - window.innerWidth,
      hero_height_px: hero ? Math.round(hero.getBoundingClientRect().height) : 0,
      preset: body.dataset.designPreset || '',
      palette: {
        paper: style.getPropertyValue('--designed-paper').trim(),
        surface: style.getPropertyValue('--designed-surface').trim(),
        surface_alt: style.getPropertyValue('--designed-surface-alt').trim(),
        accent: style.getPropertyValue('--accent').trim(),
        accent_secondary: style.getPropertyValue('--accent-secondary').trim(),
        hero_scrim: style.getPropertyValue('--hero-scrim').trim(),
      },
    };
  });
  const slug = path.basename(file, '.html');
  const screenshot = path.join(screenshotDir, `${slug}-desktop.png`);
  await page.screenshot({ path: screenshot });
  await context.close();
  return {
    slug,
    file,
    screenshot,
    console_errors: consoleErrors,
    failed_requests: failedRequests,
    remote_requests: remoteRequests,
    ...metrics,
  };
}

async function main() {
  const files = fs.readdirSync(paletteDir)
    .filter((name) => name.endsWith('.html'))
    .sort()
    .map((name) => path.join(paletteDir, name));
  const browser = await chromium.launch({ headless: true });
  const rows = [];
  for (const file of files) rows.push(await auditVariant(browser, file));
  await browser.close();

  const signatures = new Set(rows.map((row) => JSON.stringify(row.palette)));
  const pass = rows.length >= 6
    && signatures.size === rows.length
    && rows.every((row) => (
      row.overflow_px <= 1
      && row.hero_height_px > 0
      && row.hero_height_px <= 500
      && row.console_errors.length === 0
      && row.failed_requests.length === 0
      && row.remote_requests.length === 0
      && Object.values(row.palette).every(Boolean)
    ));
  const result = {
    generated_at: new Date().toISOString(),
    pass,
    variant_count: rows.length,
    unique_palette_count: signatures.size,
    rows,
  };
  fs.writeFileSync(
    path.join(paletteDir, 'palette-audit.json'),
    `${JSON.stringify(result, null, 2)}\n`,
    'utf8',
  );
  console.log(JSON.stringify(result, null, 2));
  if (!pass) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
