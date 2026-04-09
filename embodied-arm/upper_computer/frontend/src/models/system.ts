export type RuntimePhase =
  | 'boot'
  | 'idle'
  | 'perception'
  | 'plan'
  | 'execute'
  | 'verify'
  | 'safe_stop'
  | 'fault';

export type SystemMode = RuntimePhase;
export type ControllerMode = 'idle' | 'manual' | 'task' | 'maintenance';
export type TaskStage = 'created' | 'perception' | 'plan' | 'execute' | 'verify' | 'done' | 'failed';

export interface SystemState {
  runtimePhase: RuntimePhase;
  controllerMode: ControllerMode;
  taskStage: TaskStage;
  rosConnected: boolean;
  stm32Connected: boolean;
  esp32Connected: boolean;
  cameraConnected: boolean;
  emergencyStop: boolean;
  faultCode?: string;
  faultMessage?: string;
  timestamp: string;
  currentTaskId?: string;
  mode?: SystemMode;
  /** Legacy compatibility alias retained for older gateway snapshots. */
  operatorMode?: ControllerMode;
  currentStage?: string;
}

export interface HealthSummary {
  cpuUsage?: number;
  memoryUsage?: number;
  latencyMs?: number;
  packetLoss?: number;
  reconnectCount?: number;
}

const runtimePhases: RuntimePhase[] = ['boot', 'idle', 'perception', 'plan', 'execute', 'verify', 'safe_stop', 'fault'];
const controllerModes: ControllerMode[] = ['idle', 'manual', 'task', 'maintenance'];
const taskStages: TaskStage[] = ['created', 'perception', 'plan', 'execute', 'verify', 'done', 'failed'];

export function normalizeRuntimePhase(value: unknown): RuntimePhase {
  const normalized = String(value || 'idle').trim().toLowerCase() as RuntimePhase;
  return runtimePhases.includes(normalized) ? normalized : 'idle';
}

export function deriveControllerMode(runtimePhase: RuntimePhase, explicit?: unknown, emergencyStop = false): ControllerMode {
  const normalizedExplicit = String(explicit || 'idle').trim().toLowerCase() as ControllerMode;
  if (controllerModes.includes(normalizedExplicit) && ['manual', 'maintenance'].includes(normalizedExplicit)) {
    return normalizedExplicit;
  }
  if (emergencyStop || runtimePhase === 'safe_stop' || runtimePhase === 'fault') return 'maintenance';
  if (['perception', 'plan', 'execute', 'verify'].includes(runtimePhase)) return 'task';
  return controllerModes.includes(normalizedExplicit) ? normalizedExplicit : 'idle';
}

export function inferTaskStage(runtimePhase: RuntimePhase, currentStage?: unknown): TaskStage {
  const normalized = String(currentStage || '').trim().toLowerCase();
  if (taskStages.includes(normalized as TaskStage)) return normalized as TaskStage;
  if (normalized.includes('verify')) return 'verify';
  if (normalized.includes('exec')) return 'execute';
  if (normalized.includes('plan')) return 'plan';
  if (normalized.includes('wait') || normalized.includes('perception')) return 'perception';
  switch (runtimePhase) {
    case 'perception': return 'perception';
    case 'plan': return 'plan';
    case 'execute': return 'execute';
    case 'verify': return 'verify';
    case 'safe_stop':
    case 'fault': return 'failed';
    case 'idle': return 'done';
    default: return 'created';
  }
}

export function resolveControllerMode(payload: Partial<SystemState> & Record<string, unknown>): ControllerMode {
  const runtimePhase = normalizeRuntimePhase(payload.runtimePhase ?? payload.mode);
  return deriveControllerMode(runtimePhase, payload.controllerMode ?? payload.operatorMode, Boolean(payload.emergencyStop));
}

export function resolveTaskStage(payload: Partial<SystemState> & Record<string, unknown>): TaskStage {
  const runtimePhase = normalizeRuntimePhase(payload.runtimePhase ?? payload.mode);
  return inferTaskStage(runtimePhase, payload.taskStage ?? payload.currentStage);
}

export function coerceSystemState(payload: Partial<SystemState> & Record<string, unknown>): SystemState {
  const runtimePhase = normalizeRuntimePhase(payload.runtimePhase ?? payload.mode);
  const controllerMode = resolveControllerMode(payload);
  const taskStage = resolveTaskStage(payload);
  return {
    runtimePhase,
    controllerMode,
    taskStage,
    rosConnected: Boolean(payload.rosConnected),
    stm32Connected: Boolean(payload.stm32Connected),
    esp32Connected: Boolean(payload.esp32Connected),
    cameraConnected: Boolean(payload.cameraConnected),
    emergencyStop: Boolean(payload.emergencyStop),
    faultCode: typeof payload.faultCode === 'string' ? payload.faultCode : undefined,
    faultMessage: typeof payload.faultMessage === 'string' ? payload.faultMessage : undefined,
    timestamp: typeof payload.timestamp === 'string' ? payload.timestamp : new Date().toISOString(),
    currentTaskId: typeof payload.currentTaskId === 'string' ? payload.currentTaskId : '',
    mode: runtimePhase,
    operatorMode: controllerMode,
    currentStage: taskStage,
  };
}
