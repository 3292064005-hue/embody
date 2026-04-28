const buildProfile = String(process.env.VITE_BUILD_PROFILE || process.env.EMBODIED_ARM_BUILD_PROFILE || 'development').trim().toLowerCase();
const mockEnabled = String(process.env.VITE_ENABLE_MOCK || 'false').trim().toLowerCase() === 'true';
const mockMode = String(process.env.VITE_API_MOCK_MODE || '').trim().toLowerCase();

if (['release', 'production'].includes(buildProfile)) {
  if (mockEnabled) {
    console.error('[build-guard] release build forbids VITE_ENABLE_MOCK=true');
    process.exit(1);
  }
  if (mockMode && mockMode !== 'off') {
    console.error(`[build-guard] release build forbids VITE_API_MOCK_MODE=${mockMode}`);
    process.exit(1);
  }
}

console.log(`[build-guard] buildProfile=${buildProfile} mockEnabled=${mockEnabled} mockMode=${mockMode || 'off'}`);
