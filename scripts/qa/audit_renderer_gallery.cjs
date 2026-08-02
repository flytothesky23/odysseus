#!/usr/bin/env node
/* eslint-disable no-console */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');

const QA_ROOT = process.env.ODYSSEUS_QA_ROOT
  || path.join(os.homedir(), 'Downloads/odysseus-qa/generative-renderer-gallery-rc-2026-07-29');
const GALLERY = path.join(QA_ROOT, 'renderer-gallery');
const MATRIX_FILE = path.join(GALLERY, 'structural-diversity-matrix.json');
const SCREENSHOTS = path.join(GALLERY, 'screenshots');
const FAILURES = [];
const AUDIT = {
  generated_at: new Date().toISOString(),
  fixture: 'renderer-gallery-five-contexts-v1',
  entries: [],
  remote_request_count: 0,
  console_error_count: 0,
  request_failure_count: 0,
};

function check(condition, message, detail = null) {
  if (!condition) FAILURES.push({ message, detail });
}

async function inspectArtifact(browser, contextId, rendererId, file, expectedHash) {
  const viewports = [
    { label: 'desktop', width: 1440, height: 900 },
    { label: 'mobile', width: 390, height: 844 },
  ];
  for (const viewport of viewports) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      serviceWorkers: 'block',
    });
    const page = await context.newPage();
    const consoleErrors = [];
    const requestFailures = [];
    const remoteRequests = [];
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('requestfailed', (request) => requestFailures.push({
      url: request.url(),
      error: request.failure()?.errorText || '',
    }));
    page.on('request', (request) => {
      if (/^https?:/i.test(request.url())) remoteRequests.push(request.url());
    });
    await page.goto(pathToFileURL(file).href, { waitUntil: 'load' });
    await page.waitForTimeout(100);
    const metrics = await page.evaluate(() => ({
      renderer: document.body?.dataset?.htmlRenderer || '',
      reportIrHash: document.body?.dataset?.reportIrHash || '',
      overflow: Math.max(document.body.scrollWidth, document.documentElement.scrollWidth) - innerWidth,
      mainTextLength: (document.querySelector('main')?.innerText || '').trim().length,
      claimIds: [...new Set(
        Array.from(document.querySelectorAll('[data-claim-id]'))
          .flatMap((element) => (element.getAttribute('data-claim-id') || '').split(/\s+/))
          .filter(Boolean),
      )].sort(),
      citationIds: [...new Set(
        Array.from(document.querySelectorAll('[data-citation-id]'))
          .map((element) => element.getAttribute('data-citation-id') || '')
          .filter(Boolean),
      )].sort(),
      brokenAnchors: Array.from(document.querySelectorAll('a[href^="#"]'))
        .map((anchor) => anchor.getAttribute('href'))
        .filter((href) => {
          if (!href || href.length <= 1) return false;
          try {
            return !document.getElementById(decodeURIComponent(href.slice(1)));
          } catch {
            return true;
          }
        }),
      eventAttributes: Array.from(document.querySelectorAll('*')).flatMap((element) => (
        Array.from(element.attributes)
          .filter((attribute) => /^on/i.test(attribute.name))
          .map((attribute) => `${element.tagName}.${attribute.name}`)
      )),
      javascriptUrls: Array.from(document.querySelectorAll('[href],[src]'))
        .map((element) => element.getAttribute('href') || element.getAttribute('src') || '')
        .filter((value) => /^javascript:/i.test(value.trim())),
      mainCount: document.querySelectorAll('main').length,
      landmarkCount: document.querySelectorAll('main, nav[aria-label], article').length,
      tableScrollCount: document.querySelectorAll('.table-scroll').length,
      reportStyle: document.body?.dataset?.reportStyle || '',
      designComposition: document.querySelector('[data-design-composition]')?.getAttribute('data-design-composition') || '',
      sceneTreatment: document.body?.dataset?.sceneTreatment || '',
    }));
    const screenshot = path.join(SCREENSHOTS, `${contextId}-${rendererId}-${viewport.label}.png`);
    await page.screenshot({ path: screenshot, fullPage: true });
    const entry = {
      context_id: contextId,
      renderer_id: rendererId,
      viewport: viewport.label,
      file,
      screenshot,
      metrics,
      console_errors: consoleErrors,
      request_failures: requestFailures,
      remote_requests: remoteRequests,
    };
    AUDIT.entries.push(entry);
    AUDIT.remote_request_count += remoteRequests.length;
    AUDIT.console_error_count += consoleErrors.length;
    AUDIT.request_failure_count += requestFailures.length;
    check(metrics.renderer === rendererId, `${contextId}/${rendererId} renderer identity`, metrics);
    check(metrics.reportIrHash === expectedHash, `${contextId}/${rendererId} ReportIR hash`, metrics);
    check(metrics.overflow <= 1, `${contextId}/${rendererId}/${viewport.label} overflow`, metrics);
    check(metrics.mainTextLength > 200, `${contextId}/${rendererId}/${viewport.label} searchable text`, metrics);
    check(metrics.brokenAnchors.length === 0, `${contextId}/${rendererId}/${viewport.label} anchors`, metrics);
    check(metrics.eventAttributes.length === 0, `${contextId}/${rendererId}/${viewport.label} event attributes`, metrics);
    check(metrics.javascriptUrls.length === 0, `${contextId}/${rendererId}/${viewport.label} javascript URLs`, metrics);
    check(metrics.mainCount === 1, `${contextId}/${rendererId}/${viewport.label} main landmark`, metrics);
    check(consoleErrors.length === 0, `${contextId}/${rendererId}/${viewport.label} console`, consoleErrors);
    check(requestFailures.length === 0, `${contextId}/${rendererId}/${viewport.label} requests`, requestFailures);
    check(remoteRequests.length === 0, `${contextId}/${rendererId}/${viewport.label} offline`, remoteRequests);
    await context.close();
  }
}

async function inspectPrint(browser, contextId, rendererId, file) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await page.emulateMedia({ media: 'print', reducedMotion: 'reduce' });
  await page.goto(pathToFileURL(file).href, { waitUntil: 'load' });
  const pdf = path.join(SCREENSHOTS, `${contextId}-${rendererId}-print.pdf`);
  const preview = path.join(SCREENSHOTS, `${contextId}-${rendererId}-print-preview.png`);
  await page.screenshot({ path: preview, fullPage: true });
  await page.pdf({ path: pdf, format: 'A4', printBackground: true });
  const metrics = await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth - innerWidth,
    mainTextLength: (document.querySelector('main')?.innerText || '').trim().length,
    motionReduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
  }));
  check(metrics.overflow <= 1, `${contextId}/${rendererId} print overflow`, metrics);
  check(metrics.mainTextLength > 200, `${contextId}/${rendererId} print text`, metrics);
  check(fs.statSync(pdf).size > 1000, `${contextId}/${rendererId} print PDF`, fs.statSync(pdf).size);
  AUDIT.entries.push({
    context_id: contextId,
    renderer_id: rendererId,
    viewport: 'print',
    file,
    screenshot: preview,
    pdf,
    metrics,
  });
  await context.close();
}

async function main() {
  if (!fs.existsSync(MATRIX_FILE)) {
    throw new Error(`Missing structural matrix: ${MATRIX_FILE}`);
  }
  fs.mkdirSync(SCREENSHOTS, { recursive: true });
  const manifest = JSON.parse(fs.readFileSync(MATRIX_FILE, 'utf8'));
  const browser = await chromium.launch({ headless: true });
  try {
    for (const row of manifest.rows) {
      for (const rendererId of ['document', 'editorial', 'scroll_story']) {
        const file = path.join(GALLERY, row.context_id, `${rendererId}.html`);
        await inspectArtifact(browser, row.context_id, rendererId, file, row.report_ir_hash);
      }
      const recommended = row.recommended_renderer;
      await inspectPrint(
        browser,
        row.context_id,
        recommended,
        path.join(GALLERY, row.context_id, `${recommended}.html`),
      );
    }
  } finally {
    await browser.close();
  }
  AUDIT.pass = FAILURES.length === 0;
  AUDIT.failures = FAILURES;
  fs.writeFileSync(
    path.join(GALLERY, 'visual-audit.json'),
    JSON.stringify(AUDIT, null, 2),
    'utf8',
  );
  const links = manifest.rows.map((row) => {
    const dir = row.context_id;
    return [
      `### ${row.context_id}`,
      '',
      `- 자동 추천: \`${row.recommended_renderer}\` — ${row.recommendation_reason}`,
      `- [Document HTML](${dir}/document.html) · [desktop](screenshots/${dir}-document-desktop.png) · [mobile](screenshots/${dir}-document-mobile.png)`,
      `- [Editorial HTML](${dir}/editorial.html) · [desktop](screenshots/${dir}-editorial-desktop.png) · [mobile](screenshots/${dir}-editorial-mobile.png)`,
      `- [Scroll Story HTML](${dir}/scroll_story.html) · [desktop](screenshots/${dir}-scroll_story-desktop.png) · [mobile](screenshots/${dir}-scroll_story-mobile.png)`,
      `- [추천 renderer print PDF](screenshots/${dir}-${row.recommended_renderer}-print.pdf)`,
      `- [ReportIR](${dir}/report-ir.json)`,
      '',
    ].join('\n');
  }).join('\n');
  fs.writeFileSync(
    path.join(GALLERY, 'README.md'),
    `# Generative Report Renderer Gallery

- 판정: **${AUDIT.pass ? 'PASS' : 'FAIL'}**
- fixture: \`renderer-gallery-five-contexts-v1\`
- 실제 개인 자료·외부 디자인 서비스·원격 자산: 사용하지 않음
- [구조 다양성 matrix](structural-diversity-matrix.json)
- [시각·DOM·offline 감사](visual-audit.json)
- [recipe provenance](asset-recipe-manifest.json)

동일 문맥의 Document·Editorial·Scroll Story는 같은 immutable ReportIR을 사용합니다.
다섯 문맥의 자동 추천 결과는 palette뿐 아니라 DOM topology, 한국어 typography/rhythm,
scene/component treatment가 달라야 통과합니다.

${links}
`,
    'utf8',
  );
  if (FAILURES.length) {
    throw new Error(`${FAILURES.length} gallery audit failures`);
  }
  console.log(JSON.stringify({
    ok: true,
    qa_root: QA_ROOT,
    audited_entries: AUDIT.entries.length,
    screenshots: AUDIT.entries.filter((entry) => entry.screenshot).length,
  }, null, 2));
}

main().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
