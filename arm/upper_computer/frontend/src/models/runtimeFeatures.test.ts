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

  it('lists missing startTask prerequisites while keeping the workbench visible', () => {
    const state = deriveRuntimeFeatureState({
      runtimeSurfaceState: {
        runtimeTier: 'validated_sim',
        runtimeBadge: 'VALIDATED_SIM',
        runtimeLabel: 'Validated Simulation',
        taskWorkbenchVisible: true,
        taskExecutionInteractive: false,
      },
      taskExecutionState: {
        workbenchVisible: true,
        interactive: false,
        startAllowed: false,
        runtimeTier: 'validated_sim',
        reason: '',
        promotionControlled: false,
        promotionEffective: true,
        promotionMissing: [],
        startMissingDetails: [
          { name: 'camera_alive', detail: 'camera_offline' },
          { name: 'target_available', detail: 'target_unavailable' },
        ],
      },
      commandPolicies: {
        startTask: { allowed: false, reason: '' },
      },
    } as any);

    expect(state.taskWorkbenchVisible).toBe(true);
    expect(state.taskExecutionInteractive).toBe(false);
    expect(state.taskStartReason).toContain('camera_alive(camera_offline)');
    expect(state.taskStartReason).toContain('target_available(target_unavailable)');
  });

});
