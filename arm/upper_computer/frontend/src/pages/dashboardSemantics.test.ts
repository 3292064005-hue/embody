import { describe, expect, it } from 'vitest';

import { deriveCommandText, deriveDiagnosticsText, deriveModeText, deriveRuntimeText } from '@/pages/dashboardSemantics';

describe('dashboard semantics', () => {
  it('derives runtime text for healthy, simulated and blocked states', () => {
    expect(deriveRuntimeText(true, false, [])).toBe('运行时核心链路健康。');
    expect(deriveRuntimeText(true, true, [])).toBe('运行时核心健康，但当前是显式模拟 runtime。');
    expect(deriveRuntimeText(false, false, ['hardware_bridge'])).toContain('hardware_bridge');
    expect(deriveRuntimeText(false, false, [])).toBe('运行时核心尚未健康。');
  });

  it('derives mode text for ready and blocked states', () => {
    expect(deriveModeText(true, [])).toBe('当前控制模式已满足模式级门禁。');
    expect(deriveModeText(false, [{ name: 'camera_alive', detail: 'stale' }])).toContain('camera_alive: stale');
    expect(deriveModeText(false, [])).toContain('等待网关回传 readiness');
  });

  it('derives command text for empty, mixed and fully ready states', () => {
    expect(deriveCommandText(undefined, undefined)).toBe('等待命令门禁策略。');
    expect(deriveCommandText({ allowed: ['startTask'], blocked: [], readyCount: 1, blockedCount: 0 }, { startTask: { allowed: true, reason: 'ready' } })).toContain('全部可执行');
    expect(deriveCommandText(
      { allowed: ['startTask'], blocked: ['jog'], readyCount: 1, blockedCount: 1 },
      { startTask: { allowed: true, reason: 'ready' }, jog: { allowed: false, reason: 'missing readiness: hardware_bridge' } }
    )).toContain('首个阻塞：jog / missing readiness: hardware_bridge');
  });

  it('derives diagnostics text for missing and populated summaries', () => {
    expect(deriveDiagnosticsText({})).toBe('等待诊断摘要。');
    expect(deriveDiagnosticsText({ updatedAt: '2026-04-02T00:00:00Z', ready: true, degraded: false, taskSuccessRate: 95, faultCount: 1 })).toContain('successRate=95%');
  });
});
