import { describe, expect, it } from 'vitest';
import { evaluateGripper, evaluateJog, evaluateStartTask, summarizeSafetySnapshot } from '@/domain/safety/guards';
import type { SafetySnapshot } from '@/models/safety';

function baseSnapshot(): SafetySnapshot {
  return {
    operatorRole: 'maintainer',
    gatewayConnected: true,
    realtimeStale: false,
    emergencyStop: false,
    faultMode: false,
    systemBusy: false,
    hardwareBusy: false,
    homed: true,
    readonlyDegraded: false
  };
}

describe('safety guards', () => {
  it('allows task start when system is healthy', () => {
    expect(evaluateStartTask(baseSnapshot())).toEqual({ allowed: true, reason: '允许执行' });
  });

  it('blocks task start when realtime is stale', () => {
    const decision = evaluateStartTask({ ...baseSnapshot(), realtimeStale: true });
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toContain('实时链路过期');
  });

  it('uses backend command policy when provided', () => {
    const decision = evaluateStartTask({
      ...baseSnapshot(),
      commandPolicies: {
        startTask: { allowed: false, reason: 'missing readiness: camera' }
      }
    });
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toContain('camera');
  });

  it('blocks jog outside maintainer mode', () => {
    const decision = evaluateJog({ ...baseSnapshot(), operatorRole: 'operator' });
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toContain('仅维护员权限');
  });

  it('blocks gripper in viewer mode', () => {
    const decision = evaluateGripper({ ...baseSnapshot(), operatorRole: 'viewer' });
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toContain('观察者权限');
  });

  it('summarizes snapshot for audit', () => {
    const summary = summarizeSafetySnapshot(baseSnapshot());
    expect(summary).toContain('role=maintainer');
    expect(summary).toContain('gateway=online');
    expect(summary).toContain('homed=yes');
  });
});
