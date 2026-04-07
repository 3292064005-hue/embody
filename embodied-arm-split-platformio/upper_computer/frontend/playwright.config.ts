import fs from 'node:fs';
import { defineConfig, devices } from '@playwright/test';

function systemChromiumIsUsable(): boolean {
  const policyPath = '/etc/chromium/policies/managed/000_policy_merge.json';
  if (!fs.existsSync('/usr/bin/chromium')) {
    return false;
  }
  try {
    const payload = JSON.parse(fs.readFileSync(policyPath, 'utf-8')) as { URLBlocklist?: string[] };
    return !(Array.isArray(payload.URLBlocklist) && payload.URLBlocklist.includes('*'));
  } catch {
    return true;
  }
}

const launchOptions = { args: ['--no-sandbox'] };
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
  ? process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
  : systemChromiumIsUsable()
    ? '/usr/bin/chromium'
    : undefined;

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'on-first-retry'
  },
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 4173 --strictPort',
    port: 4173,
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
    env: {
      VITE_ENABLE_MOCK: 'true',
      VITE_API_MOCK_MODE: 'fixture'
    }
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions,
        ...(executablePath ? { launchOptions: { ...launchOptions, executablePath } } : {})
      }
    }
  ]
});
