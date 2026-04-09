import { deriveRuntimeFeatureState } from './runtimeFeatures';

describe('deriveRuntimeFeatureState', () => {
  it('keeps preview visibility closed when runtime tier is preview and startTask is blocked', () => {
    const state = deriveRuntimeFeatureState({
      runtimeTier: 'preview',
      productLine: 'preview',
      commandPolicies: {
        startTask: { allowed: false, reason: 'planner_backend_unavailable' },
      },
    } as any);

    expect(state.taskWorkbenchVisible).toBe(false);
    expect(state.taskExecutionInteractive).toBe(false);
    expect(state.authoritativeRuntime).toBe(false);
    expect(state.runtimeBadge).toBe('PREVIEW');
  });

  it('keeps workbench visible but execution non-interactive when authoritative tier is temporarily blocked', () => {
    const state = deriveRuntimeFeatureState({
      runtimeTier: 'validated_sim',
      commandPolicies: {
        startTask: { allowed: false, reason: 'target_unavailable' },
      },
    } as any);

    expect(state.taskWorkbenchVisible).toBe(true);
    expect(state.taskExecutionInteractive).toBe(false);
    expect(state.authoritativeRuntime).toBe(true);
    expect(state.taskStartReason).toContain('target_unavailable');
  });
});
