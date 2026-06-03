import { test, expect } from '@playwright/test';

const COOKIE_NAME = 'smart_session';

test.describe('RBAC routing', () => {
  test.skip(!process.env.E2E_BOSS_COOKIE, 'E2E_BOSS_COOKIE not set');
  test.skip(!process.env.E2E_SUPERADMIN_COOKIE, 'E2E_SUPERADMIN_COOKIE not set');

  test('boss redirected away from /superadmin/*', async ({ page, context }) => {
    await context.addCookies([{
      name: COOKIE_NAME, value: process.env.E2E_BOSS_COOKIE!,
      domain: 'localhost', path: '/',
    }]);
    await page.goto('/app/superadmin/models');
    await page.waitForURL(/\/app\/admin\//, { timeout: 8000 });
    expect(page.url()).toMatch(/\/app\/admin\//);
  });

  test('superadmin can access /admin/*', async ({ page, context }) => {
    await context.addCookies([{
      name: COOKIE_NAME, value: process.env.E2E_SUPERADMIN_COOKIE!,
      domain: 'localhost', path: '/',
    }]);
    await page.goto(`/app/admin/groups/${process.env.E2E_GROUP_ID ?? '1'}`);
    await expect(page.getByText(/thành viên/)).toBeVisible({ timeout: 10000 });
  });

  test('unauthenticated redirected to /login', async ({ page }) => {
    await page.goto('/app/admin/dashboard');
    await page.waitForURL(/\/login/, { timeout: 8000 });
    expect(page.url()).toContain('/login');
  });
});
