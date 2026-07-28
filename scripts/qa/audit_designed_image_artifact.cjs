#!/usr/bin/env node
/* eslint-disable no-console */

const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { spawnSync } = require('child_process');
const { chromium } = require('playwright');

const target = path.resolve(process.argv[2] || '');
const outputDir = path.resolve(process.argv[3] || path.dirname(target));
const baseline = process.argv[4] ? path.resolve(process.argv[4]) : null;
const screenshotDir = path.join(outputDir, 'screenshots');
const pdftoppm = process.env.ODYSSEUS_QA_PDFTOPPM || '/opt/homebrew/bin/pdftoppm';

if (!target || !fs.existsSync(target)) {
  throw new Error('Usage: audit_designed_image_artifact.cjs <html> <output-dir> [baseline-html]');
}
fs.mkdirSync(screenshotDir, { recursive: true });

async function render(browser, file, prefix, width, height) {
  const context = await browser.newContext({
    viewport: { width, height },
    serviceWorkers: 'block',
  });
  const page = await context.newPage();
  const consoleErrors = [];
  const failedRequests = [];
  const remoteRequests = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('requestfailed', (request) => failedRequests.push({
    url: request.url(),
    error: request.failure()?.errorText || '',
  }));
  page.on('request', (request) => {
    if (/^https?:/i.test(request.url())) remoteRequests.push(request.url());
  });
  await page.goto(pathToFileURL(file).href, { waitUntil: 'load' });
  await page.waitForTimeout(250);
  const audit = await page.evaluate(() => {
    const body = document.body;
    const html = document.documentElement;
    const hero = document.querySelector('.designed-hero-composer');
    const heroTitle = hero?.querySelector('h1');
    const generatedImages = Array.from(document.querySelectorAll(
      '.designed-hero-composer > img, .designed-section-visual > img, .designed-ambient-layer > img',
    ));
    const meaningfulImages = generatedImages.filter((image) => image.getAttribute('aria-hidden') !== 'true');
    const anchors = Array.from(document.querySelectorAll('a[href^="#"]'))
      .map((anchor) => anchor.getAttribute('href'))
      .filter((href) => href && href.length > 1 && !document.querySelector(href));
    const titleStyle = heroTitle ? getComputedStyle(heroTitle) : null;
    const overlay = hero
      ? Number.parseFloat(hero.style.getPropertyValue('--hero-overlay') || '0')
      : 0;
    return {
      overflow_px: Math.max(body.scrollWidth, html.scrollWidth) - window.innerWidth,
      broken_anchors: anchors,
      hero_present: Boolean(hero),
      ambient_present: Boolean(document.querySelector('.designed-ambient-layer')),
      section_background_present: Boolean(document.querySelector(
        '[data-visual-role="section_background"]',
      )),
      generated_image_count: generatedImages.length,
      missing_meaningful_alt: meaningfulImages.filter(
        (image) => !(image.getAttribute('alt') || '').trim(),
      ).length,
      hero_overlay_strength: overlay,
      hero_title_color: titleStyle?.color || '',
      design_preset: body.dataset.designPreset || '',
      variation_id: body.dataset.designVariationId || '',
      design_status: body.dataset.designAssetsStatus || '',
      manifest_present: Boolean(document.querySelector('#odysseus-design-manifest')),
    };
  });
  const screenshot = path.join(screenshotDir, `${prefix}-full.png`);
  await page.screenshot({ path: screenshot, fullPage: true });
  await context.close();
  return {
    file,
    screenshot,
    viewport: { width, height },
    console_errors: consoleErrors,
    failed_requests: failedRequests,
    remote_requests: remoteRequests,
    ...audit,
  };
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const rows = [];
  if (baseline && fs.existsSync(baseline)) {
    rows.push(await render(browser, baseline, 'round-0-reference-desktop', 1440, 900));
    rows.push(await render(browser, baseline, 'round-0-reference-mobile', 390, 844));
  }
  rows.push(await render(browser, target, 'round-2-overlay-desktop', 1440, 900));
  rows.push(await render(browser, target, 'round-2-overlay-mobile', 390, 844));

  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await page.emulateMedia({ media: 'print', reducedMotion: 'reduce' });
  await page.goto(pathToFileURL(target).href, { waitUntil: 'load' });
  const pdf = path.join(screenshotDir, 'round-2-overlay-print.pdf');
  const printPreview = path.join(screenshotDir, 'round-2-overlay-print-preview.png');
  await page.screenshot({ path: printPreview, fullPage: true });
  await page.pdf({ path: pdf, format: 'A4', printBackground: true });
  await context.close();
  await browser.close();

  const prefix = path.join(screenshotDir, 'round-2-overlay-print-page');
  const conversion = spawnSync(pdftoppm, ['-png', '-f', '1', '-singlefile', '-r', '120', pdf, prefix], {
    encoding: 'utf8',
  });
  const printPage = `${prefix}.png`;

  const finalRows = rows.filter((row) => row.file === target);
  const pass = finalRows.every((row) => (
    row.overflow_px <= 1
    && row.broken_anchors.length === 0
    && row.console_errors.length === 0
    && row.failed_requests.length === 0
    && row.remote_requests.length === 0
    && row.hero_present
    && row.ambient_present
    && row.section_background_present
    && row.generated_image_count === 3
    && row.missing_meaningful_alt === 0
    && row.hero_overlay_strength >= 0.35
    && row.manifest_present
    && row.design_status === 'ready'
  )) && conversion.status === 0 && fs.existsSync(printPage);

  const result = {
    generated_at: new Date().toISOString(),
    pass,
    target,
    baseline,
    rows,
    print: {
      pdf,
      preview: printPreview,
      page_1: printPage,
      conversion_status: conversion.status,
      conversion_error: String(conversion.stderr || '').slice(0, 500),
    },
  };
  fs.writeFileSync(
    path.join(outputDir, 'render-audit-hero-composer.json'),
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
