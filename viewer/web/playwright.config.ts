import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  testMatch: 'browser.spec.ts',
  timeout: 120_000,
  workers: 2,
  fullyParallel: true,
  retries: 0,
  reporter: [['list'], ['html', {open: 'never'}]],
  webServer: {
    command: 'node scripts/serve-test-ui.mjs',
    url: 'http://127.0.0.1:4175',
    reuseExistingServer: false,
    timeout: 15_000,
  },
});
