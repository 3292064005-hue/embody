import type { RuntimeReadiness } from '../api/generated';

export function buildRuntimeReadinessMock(overrides: Partial<RuntimeReadiness> = {}): RuntimeReadiness {
  return {
    mode: 'bootstrap',
    allReady: false,
    checks: {},
    runtimeHealthy: false,
    modeReady: false,
    runtimeTier: 'preview',
    productLine: 'preview',
    commandPolicies: {
      startTask: { allowed: false, reason: 'planner_backend_unavailable' },
    },
    ...overrides,
  };
}
