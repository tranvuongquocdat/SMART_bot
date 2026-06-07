import { chromium } from '@playwright/test';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
page.on('pageerror', e => console.log('PAGEERROR:', e.message));
page.on('console', m => { if (m.type() === 'error') console.log('CONSOLE:', m.text().slice(0, 250)); });
page.on('response', r => { if (r.status() >= 400) console.log(`HTTP ${r.status()}:`, r.url()); });

await page.goto('http://localhost:8000/login');
await page.fill('input[name="email"], input[type="email"]', 'boss@local.test');
await page.fill('input[type="password"]', 'boss123');
await page.click('button[type="submit"]');
await page.waitForURL('**/app/admin/**');
await page.goto('http://localhost:8000/app/admin/channels');
await page.waitForTimeout(1000);

for (const name of ['Zalo', 'Telegram', 'Lark']) {
  await page.click(`button:has-text("${name}")`);
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `/tmp/ch-${name}.png` });
  const body = await page.textContent('body');
  if (body.includes('Có lỗi xảy ra')) console.log(`>>> ${name}: TRANG LỖI`);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
}
await browser.close();
console.log('done');
