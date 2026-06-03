import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  use: { baseURL: 'http://localhost:8000', headless: true },
  webServer: {
    command: 'echo "assume backend running on :8000"',
    port: 8000,
    reuseExistingServer: true,
  },
});
