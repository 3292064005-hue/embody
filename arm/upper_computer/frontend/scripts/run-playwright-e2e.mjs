import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const frontendDir = path.resolve(path.dirname(__filename), '..');
const repoRoot = path.resolve(frontendDir, '..');
const artifactsDir = path.join(repoRoot, 'artifacts', 'repository_validation');
const skipLog = path.join(artifactsDir, 'frontend-e2e.skip.log');
const strict = process.env.FRONTEND_E2E_STRICT === '1';

function systemChromiumBlocked() {
  const policyPath = '/etc/chromium/policies/managed/000_policy_merge.json';
  try {
    const raw = fs.readFileSync(policyPath, 'utf-8');
    const payload = JSON.parse(raw);
    return Array.isArray(payload.URLBlocklist) && payload.URLBlocklist.includes('*');
  } catch {
    return false;
  }
}

function systemChromiumUsable() {
  return fs.existsSync('/usr/bin/chromium') && !systemChromiumBlocked();
}

function hasBundledChromium() {
  const cacheRoot = path.join(os.homedir(), '.cache', 'ms-playwright');
  if (!fs.existsSync(cacheRoot)) {
    return false;
  }
  const candidates = fs.readdirSync(cacheRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && (entry.name.startsWith('chromium-') || entry.name.startsWith('chromium_headless_shell-')))
    .flatMap((entry) => [
      path.join(cacheRoot, entry.name, 'chrome-linux', 'chrome'),
      path.join(cacheRoot, entry.name, 'chrome-linux64', 'chrome'),
      path.join(cacheRoot, entry.name, 'chrome-headless-shell-linux64', 'chrome-headless-shell'),
      path.join(cacheRoot, entry.name, 'headless_shell'),
      path.join(cacheRoot, entry.name, 'chrome')
    ]);
  return candidates.some((candidate) => fs.existsSync(candidate));
}

const shouldSkip = !process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE && !systemChromiumUsable() && !hasBundledChromium();
if (shouldSkip) {
  const message = '[frontend:e2e] skipped: no usable Chromium executable is available.';
  fs.mkdirSync(artifactsDir, { recursive: true });
  fs.writeFileSync(skipLog, message + '\n', 'utf-8');
  console.log(message);
  process.exit(strict ? 1 : 0);
}

const command = process.platform === 'win32' ? 'npx.cmd' : 'npx';
const result = spawnSync(command, ['playwright', 'test'], {
  cwd: frontendDir,
  stdio: 'inherit',
  env: process.env,
});

process.exit(result.status ?? 1);
