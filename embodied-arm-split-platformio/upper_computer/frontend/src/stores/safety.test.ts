import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

import { useAppStore } from '@/stores/app';
import { useConnectionStore } from '@/stores/connection';
import { useReadinessStore } from '@/stores/readiness';
import { useRobotStore } from '@/stores/robot';
import { useSafetyStore } from '@/stores/safety';
import { useSystemStore } from '@/stores/system';
import { coerceSystemState } from '@/models/system';

describe('safety store guards', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('blocks task start when realtime is stale', () => {
    const app = useAppStore();
    const connection = useConnectionStore();
    const robot = useRobotStore();
    const readiness = useReadinessStore();
    const system = useSystemStore();
    const safety = useSafetyStore();

    app.operatorRole = 'operator';
    connection.gatewayConnected = true;
    connection.lastMessageAt = '2026-04-01T00:00:00Z';
    connection.staleAfterMs = 1;
    robot.hardware = { joints: [], gripperOpen: false, homed: true, limits: [], busy: false };
    readiness.setReadiness({ mode: 'idle', controllerMode: 'idle', runtimePhase: 'idle', taskStage: 'done', allReady: true, requiredChecks: [], missingChecks: [], missingDetails: [], checks: {}, commandPolicies: {}, updatedAt: new Date().toISOString() });
    system.current = coerceSystemState({
      runtimePhase: 'idle',
      controllerMode: 'idle',
      taskStage: 'done',
      rosConnected: true,
      stm32Connected: true,
      esp32Connected: true,
      cameraConnected: true,
      emergencyStop: false,
      timestamp: new Date().toISOString(),
    });

    expect(safety.canStartTask.allowed).toBe(false);
    expect(safety.canStartTask.reason).toContain('实时链路过期');
  });

  it('allows task start when operator is ready and system is homed', () => {
    const app = useAppStore();
    const connection = useConnectionStore();
    const robot = useRobotStore();
    const readiness = useReadinessStore();
    const system = useSystemStore();
    const safety = useSafetyStore();

    app.operatorRole = 'operator';
    connection.gatewayConnected = true;
    connection.lastMessageAt = new Date().toISOString();
    connection.staleAfterMs = 30000;
    connection.readonlyDegraded = false;
    robot.hardware = { joints: [], gripperOpen: false, homed: true, limits: [], busy: false };
    readiness.setReadiness({ mode: 'idle', controllerMode: 'idle', runtimePhase: 'idle', taskStage: 'done', allReady: true, requiredChecks: [], missingChecks: [], missingDetails: [], checks: {}, commandPolicies: {}, updatedAt: new Date().toISOString() });
    system.current = coerceSystemState({
      runtimePhase: 'idle',
      controllerMode: 'idle',
      taskStage: 'done',
      rosConnected: true,
      stm32Connected: true,
      esp32Connected: true,
      cameraConnected: true,
      emergencyStop: false,
      timestamp: new Date().toISOString(),
    });

    expect(safety.canStartTask.allowed).toBe(true);
  });
});
