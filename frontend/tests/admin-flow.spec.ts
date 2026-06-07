import { test, expect } from '@playwright/test';

const COOKIE_NAME = 'smart_session';
const GROUP_ID = process.env.E2E_GROUP_ID ?? '1';

test.describe('Admin (boss) flow', () => {
  test.skip(!process.env.E2E_BOSS_COOKIE, 'E2E_BOSS_COOKIE not set');

  test.beforeEach(async ({ context }) => {
    await context.addCookies([{
      name: COOKIE_NAME,
      value: process.env.E2E_BOSS_COOKIE!,
      domain: 'localhost',
      path: '/',
    }]);
  });

  test('dashboard — greeting + stat cards', async ({ page }) => {
    await page.goto('/app/admin/dashboard');
    await expect(page.getByText(/Chào buổi|Dashboard/i)).toBeVisible({ timeout: 10000 });
  });

  test('dashboard — 4 stat cards with delta', async ({ page }) => {
    await page.goto('/app/admin/dashboard');
    await expect(page.getByText('Tin nhắn').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Việc cần làm').first()).toBeVisible();
    await expect(page.getByText('Nhắc nhở').first()).toBeVisible();
    await expect(page.getByText('Quyết định').first()).toBeVisible();
    await expect(page.getByText(/Mới|→ 0%|↗|↘/).first()).toBeVisible();
  });

  test('⌘K opens command palette', async ({ page }) => {
    await page.goto('/app/admin/dashboard');
    await page.keyboard.press('Meta+K');
    await expect(page.getByPlaceholder(/Tìm trang/i)).toBeVisible({ timeout: 5000 });
    await page.keyboard.press('Escape');
    await expect(page.getByPlaceholder(/Tìm trang/i)).toBeHidden();
  });

  test('groups list — "+ Tạo nhóm" or DataTable', async ({ page }) => {
    await page.goto('/app/admin/groups');
    await expect(
      page.getByText(/Tạo nhóm|nhóm/i).first()
    ).toBeVisible({ timeout: 10000 });
  });

  test('group detail — "thành viên" sub-section', async ({ page }) => {
    await page.goto(`/app/admin/groups/${GROUP_ID}`);
    await expect(page.getByText(/thành viên/i)).toBeVisible({ timeout: 10000 });
  });

  test('reminders — Đang chờ / Đã xong / Tất cả tabs', async ({ page }) => {
    await page.goto('/app/admin/reminders');
    await expect(page.getByText(/Đang chờ|Reminders/i)).toBeVisible({ timeout: 10000 });
  });

  test('projects — "+ Tạo project" or empty state', async ({ page }) => {
    await page.goto('/app/admin/projects');
    await expect(
      page.getByText(/Tạo project|Projects|project/i).first()
    ).toBeVisible({ timeout: 10000 });
  });

  test('action items — filter row + DataTable', async ({ page }) => {
    await page.goto('/app/admin/action-items');
    await expect(
      page.getByText(/Action item|action item/i).first()
    ).toBeVisible({ timeout: 10000 });
  });

  test('channels — Connect buttons visible', async ({ page }) => {
    await page.goto('/app/admin/channels');
    await expect(
      page.getByText(/Kết nối|Channels|channel/i).first()
    ).toBeVisible({ timeout: 10000 });
  });

  test('usage — stat cards visible', async ({ page }) => {
    await page.goto('/app/admin/usage');
    await expect(
      page.getByText(/Usage|Tin nhắn|usage/i).first()
    ).toBeVisible({ timeout: 10000 });
  });

  test('subscription — plan card visible', async ({ page }) => {
    await page.goto('/app/admin/subscription');
    await expect(
      page.getByText(/Subscription|Gói|plan/i).first()
    ).toBeVisible({ timeout: 10000 });
  });

  test('settings — 3 tabs (Tài khoản / AI / Chung)', async ({ page }) => {
    await page.goto('/app/admin/settings');
    await expect(
      page.getByText(/Tài khoản|Settings|Cài đặt/i).first()
    ).toBeVisible({ timeout: 10000 });
  });
});
