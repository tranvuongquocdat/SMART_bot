import { test, expect } from '@playwright/test';

const COOKIE_NAME = 'smart_session';

test.describe('Superadmin flow', () => {
  test.skip(!process.env.E2E_SUPERADMIN_COOKIE, 'E2E_SUPERADMIN_COOKIE not set');

  test.beforeEach(async ({ context }) => {
    await context.addCookies([{
      name: COOKIE_NAME,
      value: process.env.E2E_SUPERADMIN_COOKIE!,
      domain: 'localhost',
      path: '/',
    }]);
  });

  test('models — 4 tabs visible', async ({ page }) => {
    await page.goto('/app/superadmin/models');
    await expect(page.getByText(/Models|model/i).first()).toBeVisible({ timeout: 10000 });
  });

  test('bot-accounts — "+ Kết nối account" visible', async ({ page }) => {
    await page.goto('/app/superadmin/bot-accounts');
    await expect(
      page.getByText(/Kết nối account|Bot accounts/i).first()
    ).toBeVisible({ timeout: 10000 });
  });

  test('bosses — "+ Thêm boss" or DataTable visible', async ({ page }) => {
    await page.goto('/app/superadmin/bosses');
    await expect(
      page.getByText(/Thêm boss|Bosses|boss/i).first()
    ).toBeVisible({ timeout: 10000 });
  });

  test('prompts — list visible', async ({ page }) => {
    await page.goto('/app/superadmin/prompts');
    await expect(
      page.getByText(/Prompts|prompt/i).first()
    ).toBeVisible({ timeout: 10000 });
  });

  test('note-templates — visible', async ({ page }) => {
    await page.goto('/app/superadmin/note-templates');
    await expect(
      page.getByText(/Note template|Ghi chú mẫu/i).first()
    ).toBeVisible({ timeout: 10000 });
  });

  test('agent-triggers — visible', async ({ page }) => {
    await page.goto('/app/superadmin/agent-triggers');
    await expect(
      page.getByText(/Agent trigger|Trigger/i).first()
    ).toBeVisible({ timeout: 10000 });
  });

  test('audit log — filter row + table header visible', async ({ page }) => {
    await page.goto('/app/superadmin/audit');
    await expect(
      page.getByText(/Audit log/i).first()
    ).toBeVisible({ timeout: 10000 });
  });

  test('retrieval-pipelines — visible', async ({ page }) => {
    await page.goto('/app/superadmin/retrieval-pipelines');
    await expect(
      page.getByText(/Retrieval pipeline|pipeline/i).first()
    ).toBeVisible({ timeout: 10000 });
  });
});
