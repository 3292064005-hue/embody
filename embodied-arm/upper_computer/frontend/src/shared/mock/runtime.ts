import {
  mockCalibration,
  mockCalibrationVersions,
  mockHardwareState,
  mockLogs,
  mockSystemState,
  mockTask,
  mockTaskHistory,
  mockTargets,
  mockTemplates,
  mockVisionFrame,
} from '@/utils/mock';
import type { CalibrationProfile, CalibrationProfileVersion, VisionFrame, VisionTarget } from '@/models/vision';
import type { HardwareState } from '@/models/robot';
import type { LogEvent } from '@/models/log';
import type { TaskHistoryEntry, TaskProgress, TaskTemplate, TargetCategory } from '@/models/task';
import type { SystemState, ControllerMode } from '@/models/system';
import { coerceSystemState } from '@/models/system';
import type { ReadinessState } from '@/models/readiness';
import type { DiagnosticsSummary } from '@/models/diagnostics';
import type { CommandAuditRecord } from '@/models/audit';
import { generateRequestId } from '@/utils/id';

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function createReadiness(system: SystemState): ReadinessState {
  return {
    mode: system.controllerMode,
    controllerMode: system.controllerMode,
    runtimePhase: system.runtimePhase,
    taskStage: system.taskStage,
    runtimeHealthy: true,
    modeReady: !system.emergencyStop,
    allReady: !system.emergencyStop,
    runtimeRequiredChecks: ['ros2', 'task_orchestrator', 'motion_planner', 'motion_executor', 'hardware_bridge', 'calibration', 'profiles'],
    runtimeMissingChecks: [],
    requiredChecks: ['ros2', 'task_orchestrator', 'hardware_bridge', 'calibration', 'profiles'],
    missingChecks: [],
    missingDetails: [],
    checks: {
      ros2: { ok: true, detail: 'simulated_gateway_contract' },
      task_orchestrator: { ok: true, detail: 'fixture_replay' },
      motion_planner: { ok: true, detail: 'fixture_replay' },
      motion_executor: { ok: true, detail: 'fixture_replay' },
      hardware_bridge: { ok: true, detail: 'fixture_replay' },
      camera: { ok: true, detail: 'fixture_replay' },
      camera_alive: { ok: true, detail: 'fixture_replay' },
      perception_alive: { ok: true, detail: 'fixture_replay' },
      target_available: { ok: true, detail: 'fixture_available' },
      calibration: { ok: true, detail: 'fixture_loaded' },
      profiles: { ok: true, detail: 'fixture_loaded' },
    },
    commandPolicies: {
      startTask: { allowed: !system.emergencyStop, reason: system.emergencyStop ? 'fixture_estop_active' : 'fixture_ready' },
      stopTask: { allowed: true, reason: 'fixture_available' },
      jog: { allowed: system.controllerMode === 'manual' || system.controllerMode === 'maintenance', reason: 'fixture_local_command' },
      servoCartesian: { allowed: system.controllerMode === 'manual' || system.controllerMode === 'maintenance', reason: 'fixture_local_command' },
      gripper: { allowed: system.controllerMode === 'manual' || system.controllerMode === 'maintenance', reason: 'fixture_local_command' },
      home: { allowed: !system.emergencyStop, reason: system.emergencyStop ? 'fixture_estop_active' : 'fixture_ready' },
      resetFault: { allowed: system.emergencyStop, reason: system.emergencyStop ? 'fixture_estop_active' : 'fixture_no_fault' },
      recover: { allowed: true, reason: 'fixture_available' },
    },
    commandSummary: {
      allowed: [],
      blocked: [],
      readyCount: 0,
      blockedCount: 0,
    },
    authoritative: false,
    simulated: true,
    runtimeTier: 'preview',
    productLine: 'preview',
    manualCommandLimits: {
      maxServoCartesianDeltaMeters: 0.1,
      maxJogJointStepDeg: 10.0,
    },
    runtimeConfigVersion: 'fixture-runtime-config-v1',
    source: 'frontend_fixture_replay',
    updatedAt: new Date().toISOString(),
  };
}

function createDiagnostics(readiness: ReadinessState, logs: LogEvent[]): DiagnosticsSummary {
  const successHistory = mockTaskHistory.filter((item) => item.success).length;
  const successRate = mockTaskHistory.length ? Math.round((successHistory / mockTaskHistory.length) * 100) : null;
  return {
    ready: readiness.modeReady ?? readiness.allReady,
    latencyMs: 12,
    taskSuccessRate: successRate,
    faultCount: logs.filter((item) => item.level === 'fault' || item.level === 'error').length,
    degraded: !(readiness.modeReady ?? readiness.allReady),
    detail: (readiness.modeReady ?? readiness.allReady) ? 'fixture_replay_ready' : 'fixture_replay_blocked',
    updatedAt: new Date().toISOString(),
    observability: {
      queueDepth: 0,
      droppedRecords: 0,
      strictSync: false,
      lastFlushAt: null,
      lastFlushDurationMs: null,
      lastFsyncDurationMs: null,
      lastError: null,
    },
  };
}

class FixtureReplayRuntime {
  private system: SystemState = clone(mockSystemState);
  private hardware: HardwareState = clone(mockHardwareState);
  private calibration: CalibrationProfile = clone(mockCalibration);
  private calibrationVersions: CalibrationProfileVersion[] = clone(mockCalibrationVersions);
  private currentTask: TaskProgress | null = clone(mockTask);
  private logs: LogEvent[] = clone(mockLogs);
  private audits: CommandAuditRecord[] = [];

  private systemSnapshot(): SystemState {
    return coerceSystemState({ ...this.system, timestamp: new Date().toISOString() });
  }

  private readinessSnapshot(): ReadinessState {
    const readiness = createReadiness(this.systemSnapshot());
    const commandPolicies = readiness.commandPolicies || {};
    const allowed = Object.entries(commandPolicies)
      .filter(([, item]) => item.allowed)
      .map(([name]) => name);
    const blocked = Object.entries(commandPolicies)
      .filter(([, item]) => !item.allowed)
      .map(([name]) => name);
    readiness.commandSummary = {
      allowed,
      blocked,
      readyCount: allowed.length,
      blockedCount: blocked.length,
    };
    return readiness;
  }

  private diagnosticsSnapshot(): DiagnosticsSummary {
    return createDiagnostics(this.readinessSnapshot(), this.logs);
  }

  private pushLog(partial: Omit<LogEvent, 'id' | 'timestamp' | 'requestId' | 'correlationId'> & Partial<Pick<LogEvent, 'requestId' | 'correlationId'>>): void {
    const event: LogEvent = {
      id: `fixture-log-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      timestamp: new Date().toISOString(),
      requestId: partial.requestId || generateRequestId(),
      correlationId: partial.correlationId || `fixture-corr-${Date.now()}`,
      ...partial,
    };
    this.logs = [event, ...this.logs].slice(0, 400);
  }

  private pushAudit(action: string, status: CommandAuditRecord['status'], reason: string, payload?: Record<string, unknown>): void {
    this.audits = [
      {
        id: `fixture-audit-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        requestId: generateRequestId(),
        action,
        actorRole: 'maintainer' as const,
        createdAt: new Date().toISOString(),
        status,
        reason,
        payload,
      },
      ...this.audits,
    ].slice(0, 200);
  }

  private setControllerModeInternal(mode: ControllerMode): void {
    this.system = this.systemSnapshot();
    this.system.controllerMode = mode;
    if (mode === 'manual' || mode === 'maintenance') {
      this.system.runtimePhase = 'idle';
    }
  }

  getSystemSummary(): SystemState {
    return this.systemSnapshot();
  }

  getReadiness(): ReadinessState {
    return clone(this.readinessSnapshot());
  }

  getDiagnosticsSummary(): DiagnosticsSummary {
    return clone(this.diagnosticsSnapshot());
  }

  homeRobot(): null {
    this.system = this.systemSnapshot();
    this.system.runtimePhase = 'idle';
    this.system.taskStage = 'done';
    this.system.emergencyStop = false;
    this.hardware = { ...clone(this.hardware), homed: true, busy: false };
    this.pushLog({ level: 'info', module: 'mock.fixture', event: 'system.home', message: 'Fixture replay: home acknowledged' });
    this.pushAudit('system.home', 'success', 'Fixture replay: home acknowledged');
    return null;
  }

  resetFault(): null {
    this.system = this.systemSnapshot();
    this.system.emergencyStop = false;
    this.system.runtimePhase = 'idle';
    this.system.taskStage = 'done';
    this.pushLog({ level: 'info', module: 'mock.fixture', event: 'system.reset_fault', message: 'Fixture replay: reset fault acknowledged' });
    this.pushAudit('system.reset_fault', 'success', 'Fixture replay: reset fault acknowledged');
    return null;
  }

  emergencyStop(): null {
    this.system = this.systemSnapshot();
    this.system.emergencyStop = true;
    this.system.runtimePhase = 'safe_stop';
    this.system.taskStage = 'failed';
    this.setControllerModeInternal('maintenance');
    this.hardware = { ...clone(this.hardware), busy: false };
    this.pushLog({ level: 'fault', module: 'mock.fixture', event: 'system.emergency_stop', message: 'Fixture replay: emergency stop asserted' });
    this.pushAudit('system.emergency_stop', 'accepted', 'Fixture replay: emergency stop asserted');
    return null;
  }


  recoverRuntime(): null {
    this.system = this.systemSnapshot();
    this.system.emergencyStop = false;
    this.system.runtimePhase = 'idle';
    this.system.taskStage = 'done';
    this.pushLog({ level: 'info', module: 'mock.fixture', event: 'system.recover', message: 'Fixture replay: runtime recover acknowledged' });
    this.pushAudit('system.recover', 'success', 'Fixture replay: runtime recover acknowledged');
    return null;
  }

  getCurrentTask(): TaskProgress | null {
    return clone(this.currentTask);
  }

  getTaskTemplates(): TaskTemplate[] { return clone(mockTemplates); }
  getTaskHistory(): TaskHistoryEntry[] { return clone(mockTaskHistory); }

  startTask(payload: Record<string, unknown>): { taskId: string; taskRunId: string; templateId: string; runtimeTier: 'preview' | 'validated_sim' | 'validated_live'; productLine: string } {
    const taskType = String(payload.taskType || 'pick_place') as TaskProgress['taskType'];
    const targetCategory = payload.targetCategory ? (String(payload.targetCategory) as TargetCategory) : undefined;
    const templateId = String(payload.templateId || taskType);
    const taskId = `fixture-task-${Date.now()}`;
    const taskRunId = `fixture-run-${Date.now()}`;
    this.currentTask = {
      taskId,
      templateId,
      taskType,
      stage: 'created',
      percent: 0,
      retryCount: 0,
      startedAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      targetCategory,
      runtimeTier: this.getReadiness().runtimeTier,
      lastMessage: 'Fixture replay created task record',
    };
    this.system = this.systemSnapshot();
    this.system.runtimePhase = 'perception';
    this.system.taskStage = 'created';
    this.setControllerModeInternal('task');
    this.pushLog({ level: 'info', module: 'mock.fixture', event: 'task.start', taskId: taskId, message: `Fixture replay: task ${taskType} requested` });
    this.pushAudit('task.start', 'accepted', `Fixture replay: task ${taskType} requested`, payload);
    return {
      taskId,
      taskRunId,
      templateId,
      runtimeTier: this.getReadiness().runtimeTier || 'preview',
      productLine: this.getReadiness().productLine || 'preview',
    };
  }

  stopTask(): null {
    if (this.currentTask) {
      this.currentTask = { ...clone(this.currentTask), stage: 'failed', updatedAt: new Date().toISOString(), lastMessage: 'Fixture replay stopped task record' };
    }
    this.system = this.systemSnapshot();
    this.system.runtimePhase = 'safe_stop';
    this.system.taskStage = 'failed';
    this.setControllerModeInternal('maintenance');
    this.pushLog({ level: 'warn', module: 'mock.fixture', event: 'task.stop', message: 'Fixture replay: stop task acknowledged' });
    this.pushAudit('task.stop', 'accepted', 'Fixture replay: stop task acknowledged');
    return null;
  }

  getTargets(): VisionTarget[] { return clone(mockTargets); }
  getVisionFrame(): VisionFrame { return clone({ ...mockVisionFrame, targetCount: mockTargets.length }); }
  getCalibrationProfile(): CalibrationProfile { return clone(this.calibration); }
  getCalibrationVersions(): CalibrationProfileVersion[] { return clone(this.calibrationVersions); }

  saveCalibrationProfile(payload: Record<string, unknown>): null {
    const profile = payload as unknown as CalibrationProfile;
    this.calibration = { ...clone(profile), updatedAt: new Date().toISOString() };
    const nextVersion: CalibrationProfileVersion = {
      id: `fixture-cal-${Date.now()}`,
      operator: 'maintainer',
      meanErrorMm: 1.2,
      maxErrorMm: 2.8,
      sampleCount: 24,
      active: true,
      ...clone(this.calibration),
    };
    this.calibrationVersions = [nextVersion, ...this.calibrationVersions.map((item) => ({ ...item, active: false }))].slice(0, 10);
    this.pushLog({ level: 'info', module: 'mock.fixture', event: 'calibration.save', message: 'Fixture replay: calibration saved locally' });
    this.pushAudit('calibration.save', 'success', 'Fixture replay: calibration saved locally');
    return null;
  }

  activateCalibrationProfile(profileId: string): null {
    this.calibrationVersions = this.calibrationVersions.map((item) => ({ ...item, active: item.id === profileId }));
    const active = this.calibrationVersions.find((item) => item.id === profileId);
    if (active) {
      this.calibration = {
        profileName: active.profileName,
        roi: active.roi,
        tableScaleMmPerPixel: active.tableScaleMmPerPixel,
        offsets: active.offsets,
        updatedAt: new Date().toISOString(),
      };
    }
    this.pushLog({ level: 'info', module: 'mock.fixture', event: 'calibration.activate', message: `Fixture replay: calibration ${profileId} activated` });
    this.pushAudit('calibration.activate', 'success', `Fixture replay: calibration ${profileId} activated`);
    return null;
  }

  getHardwareState(): HardwareState { return clone(this.hardware); }

  commandGripper(open: boolean): null {
    this.hardware = { ...clone(this.hardware), gripperOpen: open };
    this.pushLog({ level: 'info', module: 'mock.fixture', event: open ? 'gripper.open' : 'gripper.close', message: `Fixture replay: gripper ${open ? 'open' : 'close'}` });
    this.pushAudit('hardware.gripper', 'success', `Fixture replay: gripper ${open ? 'open' : 'close'}`, { open });
    return null;
  }

  jogJoint(jointIndex: number, direction: -1 | 1, stepDeg: number): null {
    const joints = [...this.hardware.joints];
    if (jointIndex >= 0 && jointIndex < joints.length) {
      joints[jointIndex] = Number((joints[jointIndex] + direction * (stepDeg * Math.PI / 180)).toFixed(4));
      this.hardware = { ...clone(this.hardware), joints };
    }
    this.pushLog({ level: 'warn', module: 'mock.fixture', event: 'joint.jog', message: `Fixture replay: J${jointIndex + 1} jog ${stepDeg}°` });
    this.pushAudit('hardware.jog_joint', 'success', 'Fixture replay: joint jog recorded', { jointIndex, direction, stepDeg });
    return null;
  }

  servoCartesian(axis: string, delta: number): null {
    this.hardware = {
      ...clone(this.hardware),
      poseName: `fixture_servo_${axis}`,
      rawStatus: { ...(this.hardware.rawStatus || {}), servoCartesian: { axis, delta } },
    };
    this.pushLog({ level: 'warn', module: 'mock.fixture', event: 'servo.cartesian', message: `Fixture replay: servo ${axis} delta=${delta}` });
    this.pushAudit('hardware.servo_cartesian', 'success', 'Fixture replay: cartesian servo recorded', { axis, delta });
    return null;
  }

  setControllerMode(mode: string): null {
    const normalized = (['idle', 'manual', 'task', 'maintenance'].includes(mode) ? mode : 'idle') as ControllerMode;
    this.setControllerModeInternal(normalized);
    this.pushLog({ level: 'info', module: 'mock.fixture', event: 'controller.mode', message: `Fixture replay: controller mode ${normalized}` });
    this.pushAudit('hardware.set_mode', 'accepted', `Fixture replay: controller mode ${normalized}`, { mode: normalized });
    return null;
  }

  getLogs(): LogEvent[] { return clone(this.logs); }
  getAuditLogs(): CommandAuditRecord[] { return clone(this.audits); }
}

export const mockRuntime = new FixtureReplayRuntime();
