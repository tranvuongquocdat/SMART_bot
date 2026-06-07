import { chromium } from '@playwright/test';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
page.on('pageerror', e => console.log('PAGEERROR:', e.message));
page.on('console', m => { if (m.type() === 'error') console.log('CONSOLE:', m.text().slice(0, 300)); });

await page.goto('http://localhost:8000/login');
await page.fill('input[type="email"]', 'boss@local.test');
await page.fill('input[type="password"]', 'boss123');
await page.click('button[type="submit"]');
await page.waitForURL('**/app/admin/**');
await page.waitForTimeout(800);

// mở hamburger menu rồi bấm Channels (SPA navigation)
await page.click('button[aria-label="Mở menu"]');
await page.waitForTimeout(400);
await page.click('a:has-text("Channels")');
await page.waitForTimeout(1500);
const body = await page.textContent('body');
console.log(body.includes('Có lỗi xảy ra') ? '>>> TRANG LỖI' : 'OK - không lỗi');
await page.screenshot({ path: '/tmp/ch-nav.png' });
await browser.close();
