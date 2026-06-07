import { chromium } from '@playwright/test';

const browser = await chromium.launch();

async function check(name, url, viewport) {
  const page = await browser.newPage({ viewport });
  page.on('pageerror', e => console.log(`[${name}] PAGEERROR:`, e.message));
  page.on('console', m => { if (m.type() === 'error') console.log(`[${name}] CONSOLE:`, m.text().slice(0, 300)); });
  page.on('response', r => { if (r.status() >= 400) console.log(`[${name}] HTTP ${r.status()}:`, r.url()); });

  await page.goto('http://localhost:8000/login');
  await page.fill('input[type="email"], input[name="email"]', 'boss@local.test');
  await page.fill('input[type="password"], input[name="password"]', 'boss123');
  await page.click('button[type="submit"]');
  await page.waitForURL('**/app/admin/**', { timeout: 10000 });

  await page.goto(`http://localhost:8000${url}`);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `/tmp/err-${name}.png` });
  await page.close();
}

await check('settings-desktop', '/app/admin/settings', { width: 1440, height: 900 });
await check('channels-mobile', '/app/admin/channels', { width: 390, height: 844 });
await browser.close();
console.log('done');
