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
  const userInput = page.locator('input[name="username"], #username, #login-username, input[autocomplete="username"], input[type="text"]').first();
  const passwordInput = page.locator('input[name="password"], #password, #login-password, input[autocomplete="current-password"], input[type="password"]').first();
  const needsLogin = await userInput.isVisible().catch(() => false);
  if (!needsLogin) return;
  assertOk(username && password, 'Login page detected. Set ODYSSEUS_E2E_USERNAME and ODYSSEUS_E2E_PASSWORD, or run a temporary server with AUTH_ENABLED=false.');
  await userInput.fill(username);
  await passwordInput.fill(password);
  await page.locator('button[type="submit"], button:has-text("Sign In"), button:has-text("로그인")').first().click();
  await page.waitForURL((url) => !/login/i.test(url.pathname), { timeout: 15000 });
}

async function clickFirstVisible(locator, description) {
  const count = await locator.count();
  for (let i = 0; i < count; i += 1) {
    const item = locator.nth(i);
    if (await item.isVisible().catch(() => false)) {
      await item.click();
      return;
    }
  }
  throw new Error(`No visible ${description} found`);
}

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });

  try {
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await maybeLogin(page);
    await page.waitForSelector('#sidebar, #message', { timeout: 20000 });
    await page.waitForFunction(() => window.__odysseusKoLocaleReady === true, null, { timeout: 10000 });
    await page.waitForFunction(() => document.body.innerText.includes('새 채팅') && document.body.innerText.includes('AI 기억'), null, { timeout: 10000 });
    const baseKoState = await page.evaluate(() => ({
      lang: document.documentElement.lang,
      messagePlaceholder: document.querySelector('#message')?.getAttribute('placeholder') || '',
      reasoningVisible: !!document.querySelector('#reasoning-effort-select'),
    }));
    assertOk(baseKoState.lang === 'ko', 'Document language should be Korean.', baseKoState);
    assertOk(baseKoState.messagePlaceholder.includes('Odysseus에게'), 'Chat message placeholder is not Korean.', baseKoState);
    assertOk(baseKoState.reasoningVisible, 'Reasoning effort selector is missing.', baseKoState);

    await page.locator('#model-picker-btn').click();
    await page.waitForSelector('#model-picker-menu:not(.hidden)', { timeout: 5000 });
    await page.waitForFunction(() => (document.querySelector('#model-picker-search')?.placeholder || '').includes('모델'), null, { timeout: 10000 });
    await page.waitForTimeout(500);

    const modelMetrics = await page.evaluate(() => {
      const menu = document.querySelector('#model-picker-menu');
      const rows = Array.from(document.querySelectorAll('#model-picker-list .model-switch-item'));
      const firstRow = rows[0] || null;
      const style = firstRow ? getComputedStyle(firstRow) : null;
      const ep = firstRow?.querySelector('.model-switch-ep') || null;
      return {
        menuWidth: menu ? Math.round(menu.getBoundingClientRect().width) : 0,
        rowCount: rows.length,
        rowFontSize: style ? parseFloat(style.fontSize) : null,
        endpointFontSize: ep ? parseFloat(getComputedStyle(ep).fontSize) : null,
        rowOverflowCount: rows.filter((row) => row.scrollWidth > row.clientWidth + 1).length,
        visibleRows: rows.slice(0, 5).map((row) => row.innerText.trim()),
      };
    });

    assertOk(modelMetrics.menuWidth >= 420, 'Model picker menu is still too narrow.', modelMetrics);
    assertOk(!modelMetrics.rowFontSize || modelMetrics.rowFontSize <= 13, 'Model picker row font is too large.', modelMetrics);
    assertOk(modelMetrics.rowOverflowCount === 0, 'Model picker rows overflow horizontally.', modelMetrics);

    await page.keyboard.press('Escape');
    await page.waitForFunction(() => document.querySelector('#model-picker-menu')?.classList.contains('hidden'), null, { timeout: 1000 });
    const effortSelect = page.locator('#reasoning-effort-select');
    await effortSelect.selectOption('high');
    const effortState = await page.evaluate(() => ({
      disabled: document.querySelector('#reasoning-effort-select')?.disabled,
      value: document.querySelector('#reasoning-effort-select')?.value || '',
      storage: localStorage.getItem('odysseus-model-reasoning-effort') || '',
    }));
    assertOk(effortState.disabled === false, 'Reasoning effort selector should be enabled when a model is selected.', effortState);
    assertOk(effortState.value === 'high' && effortState.storage.includes('"high"'), 'Reasoning effort selection was not persisted per model.', effortState);

    await clickFirstVisible(page.locator('#tool-memory-btn, #rail-memory'), 'AI memory button');
    await page.waitForSelector('#memory-modal:not(.hidden)', { timeout: 5000 });
    await page.waitForFunction(() => document.querySelector('#model-picker-menu')?.classList.contains('hidden'), null, { timeout: 1000 });
    await page.waitForFunction(() => {
      const text = document.querySelector('#memory-modal')?.innerText || '';
      const hasMemoryContent = !!document.querySelector('#memory-list .memory-item')
        || text.includes('아직 기억이 없습니다');
      return text.includes('AI 기억') && text.includes('기능') && hasMemoryContent;
    }, null, { timeout: 10000 });
    const memoryToggleText = await page.evaluate(() => {
      const el = document.querySelector('#memory-modal .admin-toggle-state');
      return el ? getComputedStyle(el, '::before').content.replace(/^"|"$/g, '') : '';
    });
    assertOk(memoryToggleText.includes('사용'), 'Memory toggle pseudo-label is not Korean.', { memoryToggleText });

    await page.keyboard.press('Escape');
    await page.waitForFunction(() => {
      const modal = document.querySelector('#memory-modal');
      return !modal || modal.classList.contains('hidden') || getComputedStyle(modal).display === 'none';
    }, null, { timeout: 3000 }).catch(() => {});
    const memoryStillOpen = await page.evaluate(() => {
      const modal = document.querySelector('#memory-modal');
      return !!modal && !modal.classList.contains('hidden') && getComputedStyle(modal).display !== 'none';
    });
    if (memoryStillOpen) {
      await clickFirstVisible(page.locator('#memory-modal .close-btn, #memory-modal button[title="Close"], #memory-modal button[title="닫기"]'), 'memory close button');
    }

    await clickFirstVisible(page.locator('#rail-research, #tool-research-btn'), 'research button');
    await page.waitForSelector('#research-pane', { timeout: 5000 });
    const outputFormats = await page.evaluate(() => {
      const checks = Array.from(document.querySelectorAll('input[name="research-output-format"]'));
      return checks.map((el) => ({
        id: el.id,
        value: el.value,
        checked: el.checked,
        label: el.closest('label')?.textContent?.trim() || '',
      }));
    });
    assertOk(outputFormats.some((item) => item.value === 'html' && item.checked), 'Research output selector should default to HTML.', { outputFormats });
    assertOk(outputFormats.some((item) => item.value === 'md_json'), 'Research output selector is missing MD+JSON.', { outputFormats });
    await page.locator('#research-output-md-json').check();
    await page.locator('#research-output-html').uncheck();
    await page.locator('#research-output-md-json').click();
    const outputGuard = await page.evaluate(() => ({
      checked: Array.from(document.querySelectorAll('input[name="research-output-format"]:checked')).map((el) => el.value),
    }));
    assertOk(outputGuard.checked.length === 1 && outputGuard.checked.includes('md_json'), 'Research output selector allowed all formats to be unchecked.', outputGuard);
    const sourceOptions = await page.locator('#research-source-mode option').evaluateAll((options) =>
      options.map((option) => ({ value: option.value, text: option.textContent.trim() }))
    );
    const expectedSourceValues = ['', 'web', 'local', 'web_local', 'obsidian', 'web_obsidian', 'web_all'];
    assertOk(
      expectedSourceValues.every((value) => sourceOptions.some((option) => option.value === value)),
      'Research source dropdown is missing Obsidian/local source combinations.',
      { sourceOptions }
    );
    await page.locator('#research-source-mode').selectOption('obsidian');
    await page.waitForSelector('#research-knowledge-setting', { timeout: 3000 });
    const researchSourceState = await page.evaluate(() => {
      const pane = document.querySelector('#research-pane');
      const source = document.querySelector('#research-source-mode');
      const row = document.querySelector('#research-knowledge-setting');
      const button = document.querySelector('#research-add-local-folder');
      const select = document.querySelector('#research-knowledge-folders');
      const rowBox = row?.getBoundingClientRect();
      const paneBox = pane?.getBoundingClientRect();
      return {
        sourceValue: source?.value || '',
        rowVisible: !!row && getComputedStyle(row).display !== 'none',
        buttonText: button?.textContent?.trim() || '',
        buttonVisible: !!button && getComputedStyle(button).display !== 'none',
        selectText: select?.innerText || '',
        rowWidth: rowBox ? Math.round(rowBox.width) : 0,
        paneWidth: paneBox ? Math.round(paneBox.width) : 0,
        overflow: row && pane ? row.scrollWidth > pane.clientWidth + 2 : true,
      };
    });
    assertOk(researchSourceState.sourceValue === 'obsidian', 'Research source mode did not switch to Obsidian only.', researchSourceState);
    assertOk(researchSourceState.rowVisible && researchSourceState.buttonVisible, 'Knowledge folder picker controls are not visible.', researchSourceState);
    assertOk(researchSourceState.buttonText.includes('Finder'), 'Finder folder add button is missing.', researchSourceState);
    assertOk(researchSourceState.overflow === false, 'Research knowledge source row overflows the modal.', researchSourceState);

    const englishLeaks = await page.evaluate(() => {
      const selectors = [
        '#sidebar',
        '.chat-meta-overlay',
        '#model-picker-menu:not(.hidden)',
        '#memory-modal:not(.hidden) .modal-header',
        '#memory-modal:not(.hidden) .memory-tabs',
        '#memory-modal:not(.hidden) .memory-toolbar',
      ];
      const forbidden = [
        'New Chat', 'Chats', 'Tools', 'Brain', 'Calendar', 'Compare', 'Cookbook',
        'Deep Research', 'Gallery', 'Library', 'Notes', 'Tasks', 'Theme',
        'Memories', 'Skills', 'Enabled', 'No memories yet', 'Import in Add tab',
        'Search models', 'Message Odysseus', 'User', 'You', 'Korean casual greeting',
      ];
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
    await browser.close();
  }
})().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});
