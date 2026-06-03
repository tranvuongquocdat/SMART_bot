import { test, expect } from '@playwright/test';

const COOKIE_NAME = 'smart_session';

test.describe('SPA smoke', () => {
  test.skip(!process.env.E2E_SUPERADMIN_COOKIE, 'E2E_SUPERADMIN_COOKIE not set');
  test.skip(!process.env.E2E_BOSS_COOKIE, 'E2E_BOSS_COOKIE not set');

  test('superadmin Models & Bots renders', async ({ page, context }) => {
    await context.addCookies([{
      name: COOKIE_NAME, value: process.env.E2E_SUPERADMIN_COOKIE!,
      domain: 'localhost', path: '/',
    }]);
    await page.goto('/app/superadmin/models');
    await expect(page.getByText('Models & Bots')).toBeVisible();
  });

  test('admin Group viewer renders', async ({ page, context }) => {
    await context.addCookies([{
      name: COOKIE_NAME, value: process.env.E2E_BOSS_COOKIE!,
      domain: 'localhost', path: '/',
    }]);
    await page.goto(`/app/admin/groups/${process.env.E2E_GROUP_ID ?? '1'}`);
    await expect(page.getByText(/thành viên/)).toBeVisible({ timeout: 10000 });
  });

  test('theme toggle works', async ({ page, context }) => {
    await context.addCookies([{
      name: COOKIE_NAME, value: process.env.E2E_BOSS_COOKIE!,
      domain: 'localhost', path: '/',
    }]);
    await page.goto('/app/admin/dashboard');
    const html = page.locator('html');
    const initial = await html.getAttribute('class');
    await page.getByLabel('Đổi theme').click();
    await expect(html).not.toHaveAttribute('class', initial ?? '');
  });
});
