#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const baseUrl = process.env.ODYSSEUS_E2E_URL || 'http://127.0.0.1:7860';
const outDir = process.env.ODYSSEUS_E2E_OUT || path.join(process.cwd(), 'output', 'playwright');
const username = process.env.ODYSSEUS_E2E_USERNAME || '';
const password = process.env.ODYSSEUS_E2E_PASSWORD || '';

function assertOk(condition, message, detail) {
  if (!condition) {
    const suffix = detail ? `\n${JSON.stringify(detail, null, 2)}` : '';
    throw new Error(`${message}${suffix}`);
  }
}

async function maybeLogin(page) {
  const userInput = page.locator('input[name="username"], #username, input[autocomplete="username"], input[type="text"]').first();
  const passwordInput = page.locator('input[name="password"], #password, input[autocomplete="current-password"], input[type="password"]').first();
  const needsLogin = await userInput.isVisible().catch(() => false);
  if (!needsLogin) return;
  await page.waitForFunction(() => window.__odysseusKoLocaleReady === true, null, { timeout: 10000 });
  const loginState = await page.evaluate(() => ({
    lang: document.documentElement.lang,
    submit: document.querySelector('#submitBtn')?.textContent?.trim() || '',
    usernameLabel: document.querySelector('label[for="username"]')?.textContent?.trim() || '',
  }));
  assertOk(loginState.lang === 'ko', 'Login document language should be Korean.', loginState);
  assertOk(loginState.submit.includes('로그인'), 'Login submit button is not Korean.', loginState);
  assertOk(loginState.usernameLabel.includes('사용자'), 'Login username label is not Korean.', loginState);
  if (!username || !password) {
    throw new Error('Login page detected. Set ODYSSEUS_E2E_USERNAME and ODYSSEUS_E2E_PASSWORD, or run a temporary server with auth disabled.');
  }
  await userInput.fill(username);
  await passwordInput.fill(password);
  await page.locator('button[type="submit"], button:has-text("로그인")').first().click();
  await page.waitForURL((url) => !/login/i.test(url.pathname), { timeout: 15000 });
}

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1,
    serviceWorkers: 'block',
  });
  const page = await context.newPage();

  try {
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await maybeLogin(page);
    await page.waitForSelector('#sidebar, #message', { timeout: 20000 });
    await page.waitForFunction(() => window.__odysseusKoLocaleReady === true, null, { timeout: 10000 });
    await page.waitForFunction(() => {
      const text = document.body.innerText || '';
      return text.includes('새 채팅') && text.includes('AI 기억');
    }, null, { timeout: 10000 });

    const baseKoState = await page.evaluate(() => ({
      lang: document.documentElement.lang,
      title: document.title,
      messagePlaceholder: document.querySelector('#message')?.getAttribute('placeholder') || '',
      searchPlaceholder: document.querySelector('#search-input')?.getAttribute('placeholder') || '',
      sidebarText: document.querySelector('#sidebar')?.innerText || '',
    }));
    assertOk(baseKoState.lang === 'ko', 'Document language should be Korean.', baseKoState);
    assertOk(baseKoState.messagePlaceholder.includes('Odysseus에게'), 'Chat message placeholder is not Korean.', baseKoState);
    assertOk(baseKoState.searchPlaceholder.includes('대화'), 'Search placeholder is not Korean.', baseKoState);
    assertOk(baseKoState.sidebarText.includes('도구') && baseKoState.sidebarText.includes('AI 기억'), 'Sidebar core labels are not Korean.', baseKoState);

    await page.locator('#model-picker-btn').click();
    await page.waitForSelector('#model-picker-menu:not(.hidden)', { timeout: 5000 });
    await page.waitForFunction(() => {
      const placeholder = document.querySelector('#model-picker-search')?.placeholder || '';
      return placeholder.includes('모델') || placeholder.includes('연결된 모델');
    }, null, { timeout: 10000 });
    const modelMetrics = await page.evaluate(() => {
      const menu = document.querySelector('#model-picker-menu');
      return {
        menuWidth: menu ? Math.round(menu.getBoundingClientRect().width) : 0,
        searchPlaceholder: document.querySelector('#model-picker-search')?.getAttribute('placeholder') || '',
      };
    });
    assertOk(modelMetrics.menuWidth > 0, 'Model picker menu did not open.', modelMetrics);
    assertOk(modelMetrics.searchPlaceholder.includes('모델'), 'Model picker search placeholder is not Korean.', modelMetrics);

    await page.keyboard.press('Escape');
    await page.locator('#user-bar-settings').click();
    await page.waitForSelector('#settings-modal:not(.hidden)', { timeout: 5000 });
    await page.waitForFunction(() => {
      const text = document.querySelector('#settings-modal')?.innerText || '';
      return text.includes('설정') && text.includes('모델 추가') && text.includes('AI 기본값');
    }, null, { timeout: 10000 });

    const englishLeaks = await page.evaluate(() => {
      const selectors = [
        '#sidebar',
        '#model-picker-menu:not(.hidden)',
        '#settings-modal:not(.hidden) .settings-sidebar',
      ];
      const forbidden = ['New Chat', 'Tools', 'Brain', 'Settings', 'Add Models', 'Added Models', 'AI Defaults', 'Agent Tools', 'Users', 'System', 'Search models'];
      const visibleText = selectors
        .flatMap((selector) => Array.from(document.querySelectorAll(selector)))
        .filter((el) => el.offsetWidth || el.offsetHeight || el.getClientRects().length)
        .map((el) => el.innerText || '')
        .join('\n');
      return forbidden.filter((word) => visibleText.includes(word));
    });
    assertOk(englishLeaks.length === 0, 'Visible Korean UI still contains target English labels.', { englishLeaks });

    const screenshotPath = path.join(outDir, 'ko-localization-smoke.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(JSON.stringify({ ok: true, baseUrl, screenshotPath, modelMetrics }, null, 2));
  } finally {
    await context.close();
    await browser.close();
  }
})().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});
