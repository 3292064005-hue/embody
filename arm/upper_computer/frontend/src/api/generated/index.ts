import type { ApiResponse } from '@/models/api';
import { ApiClientError } from '@/models/api';
import { apiClient, unwrapResponse } from '@/services/api/client';
import type { DiagnosticsSummary } from '@/models/diagnostics';
import type { HardwareState } from '@/models/robot';
import type { SystemState } from '@/models/system';
import type { TaskHistoryEntry, TaskProgress, TaskTemplate } from '@/models/task';
import type { VisionTarget, VisionFrame, CalibrationProfile, CalibrationProfileVersion } from '@/models/vision';
import type { LogEvent } from '@/models/log';
import type { CommandAuditRecord } from '@/models/audit';
import type { CommandReceiptRecord } from '@/models/receipt';

export type CommandDecision = {
  allowed: boolean;
  reason?: string;
};

export type ManualCommandLimits = {
  maxServoCartesianDeltaMeters: number;
  maxJogJointStepDeg: number;
};

export type ReadinessCheck = {
  ok: boolean;
  detail: string;
  effectiveOk?: boolean;
  ageSec?: number;
  stale?: boolean;
  staleAfterSec?: number | null;
};

export type ReadinessMissingDetail = {
  name: string;
  detail: string;
};

export type ReadinessCommandPolicy = {
  allowed: boolean;
  reason: string;
};

export type CommandSummary = {
  allowed: string[];
  blocked: string[];
  readyCount: number;
  blockedCount: number;
};

export type RuntimeAuthorityHealth = {
  lifecycleActive: boolean;
  controllerManagerActive: boolean;
  hardwareBridgeReady: boolean;
  traceContinuityRequired: boolean;
  validatedLiveGateReady: boolean;
  diagnosticsOnly: boolean;
  controllerManagerObserved?: boolean;
  requiredControllersActive?: boolean;
  requiredHardwareComponentsActive?: boolean;
  controllerManagerDetail?: string;
};

export type RuntimeReadiness = {
  mode: string;
  controllerMode?: string;
  runtimePhase?: string;
  taskStage?: string;
  runtimeHealthy?: boolean;
  modeReady?: boolean;
  allReady: boolean;
  requiredChecks?: string[];
  runtimeRequiredChecks?: string[];
  missingChecks?: string[];
  runtimeMissingChecks?: string[];
  missingDetails?: ReadinessMissingDetail[];
  checks: Record<string, ReadinessCheck>;
  commandPolicies?: Record<string, ReadinessCommandPolicy>;
  commandSummary?: CommandSummary;
  runtimeAuthorityHealth?: RuntimeAuthorityHealth;
  source?: string;
  simulated?: boolean;
  authoritative?: boolean;
  runtimeTier?: 'preview' | 'validated_sim' | 'validated_live';
  productLine?: string;
  manualCommandLimits?: ManualCommandLimits;
  runtimeConfigVersion?: string;
  updatedAt?: string;
};

export type TaskType = 'pick_place' | 'sort_by_color' | 'sort_by_qr' | 'clear_table';
export type TargetCategory = 'red' | 'blue' | 'green' | 'qr_a' | 'qr_b' | 'qr_c';

export type StartTaskRequest = {
  templateId?: string | null;
  taskType?: TaskType;
  targetCategory?: TargetCategory | null;
};

export type CommandTransportResult = {
  success?: boolean;
  accepted?: boolean;
  transportAccepted?: boolean;
  commandAccepted?: boolean;
  completionPending?: boolean;
  authoritativeStatus?: 'accepted' | 'success' | 'failed' | 'blocked' | 'rejected' | 'observed' | string;
  localPreviewOnly?: boolean;
  commandMode?: string;
  executionBackbone?: string;
  message?: string;
  transportMessage?: string;
  mode?: string;
  action?: string;
  operationId?: string;
  requestId?: string;
  receiptId?: string;
  commandId?: string;
  correlationId?: string | null;
};

export type StartTaskDecision = {
  taskId: string;
  taskRunId: string;
  episodeId: string;
  templateId: string;
  pluginKey: string;
  graphKey: string;
  runtimeTier: 'preview' | 'validated_sim' | 'validated_live';
  productLine: string;
  catalogSchemaVersion: number;
  templateVersion: number;
  pluginContractVersion: number;
  success?: boolean;
  accepted?: boolean;
  authoritativeStatus?: 'accepted' | 'success' | 'failed' | 'blocked' | 'rejected' | 'observed' | string;
  completionPending?: boolean;
  localPreviewOnly?: boolean;
  message?: string;
  operationId?: string;
  requestId?: string;
  receiptId?: string;
  correlationId?: string | null;
};

export type ApiEnvelope<T> = ApiResponse<T>;

export type ApiErrorEnvelope = {
  code: number;
  error: 'forbidden' | 'readiness_blocked' | 'validation_error' | 'not_implemented' | 'not_found' | 'internal_error';
  failureClass: 'operator_blocked' | 'readiness_blocked' | 'contract_violation' | 'dependency_unavailable' | 'transient_io_failure' | 'internal_bug';
  message: string;
  requestId: string;
  timestamp: string;
  detail: string;
  operatorActionable?: boolean | null;
};

export class RuntimeApiError extends Error {
  readonly status: number;
  readonly payload?: ApiErrorEnvelope;

  constructor(status: number, message: string, payload?: ApiErrorEnvelope) {
    super(message);
    this.name = 'RuntimeApiError';
    this.status = status;
    this.payload = payload;
  }
}

export const routes = {
  systemSummary: '/api/system/summary',
  systemReadiness: '/api/system/readiness',
  systemHome: '/api/system/home',
  systemResetFault: '/api/system/reset-fault',
  systemRecover: '/api/system/recover',
  systemEmergencyStop: '/api/system/emergency-stop',
  taskCurrent: '/api/task/current',
  taskTemplates: '/api/task/templates',
  taskHistory: '/api/task/history',
  taskStart: '/api/task/start',
  taskStop: '/api/task/stop',
  hardwareState: '/api/hardware/state',
  hardwareSetMode: '/api/hardware/set-mode',
  hardwareGripper: '/api/hardware/gripper',
  hardwareJogJoint: '/api/hardware/jog-joint',
  hardwareServoCartesian: '/api/hardware/servo-cartesian',
  visionTargets: '/api/vision/targets',
  visionFrame: '/api/vision/frame',
  visionClearTargets: '/api/vision/clear-targets',
  calibrationProfile: '/api/calibration/profile',
  calibrationProfiles: '/api/calibration/profiles',
  diagnosticsSummary: '/api/diagnostics/summary',
  logsEvents: '/api/logs/events',
  logsAudit: '/api/logs/audit',
  logsReceipts: '/api/logs/receipts',
} as const;

function asRuntimeApiError(error: unknown): RuntimeApiError {
  if (error instanceof RuntimeApiError) {
    return error;
  }
  if (error instanceof ApiClientError) {
    const payload: ApiErrorEnvelope | undefined = error.code !== undefined || error.error || error.failureClass || error.requestId || error.detail
      ? {
          code: error.code ?? error.status ?? 500,
          error: (error.error as ApiErrorEnvelope['error'] | undefined) ?? 'internal_error',
          failureClass: (error.failureClass as ApiErrorEnvelope['failureClass'] | undefined) ?? 'internal_bug',
          message: error.message,
          requestId: error.requestId ?? '',
          timestamp: '',
          detail: error.detail ?? error.message,
          operatorActionable: error.operatorActionable ?? null,
        }
      : undefined;
    return new RuntimeApiError(error.status ?? payload?.code ?? 500, error.message, payload);
  }
  if (error && typeof error === 'object') {
    const payload = error as Partial<ApiErrorEnvelope> & { status?: number; message?: string };
    return new RuntimeApiError(payload.status ?? payload.code ?? 500, payload.message ?? '请求失败', payload as ApiErrorEnvelope);
  }
  return new RuntimeApiError(500, error instanceof Error ? error.message : '请求失败');
}

async function getEnvelope<T>(url: string): Promise<T> {
  try {
    return await unwrapResponse<T>(apiClient.get<ApiResponse<T>>(url));
  } catch (error) {
    throw asRuntimeApiError(error);
  }
}

async function postEnvelope<T>(url: string, payload?: unknown): Promise<T> {
  try {
    return await unwrapResponse<T>(apiClient.post<ApiResponse<T>>(url, payload));
  } catch (error) {
    throw asRuntimeApiError(error);
  }
}

async function putEnvelope<T>(url: string, payload?: unknown): Promise<T> {
  try {
    return await unwrapResponse<T>(apiClient.put<ApiResponse<T>>(url, payload));
  } catch (error) {
    throw asRuntimeApiError(error);
  }
}

export const getSystemSummary = (): Promise<SystemState> => getEnvelope<SystemState>(routes.systemSummary);
export const fetchSystemReadiness = (): Promise<RuntimeReadiness> => getEnvelope<RuntimeReadiness>(routes.systemReadiness);
export const getCurrentTask = (): Promise<TaskProgress | null> => getEnvelope<TaskProgress | null>(routes.taskCurrent);
export const getTaskTemplates = (): Promise<TaskTemplate[]> => getEnvelope<TaskTemplate[]>(routes.taskTemplates);
export const getTaskHistory = (): Promise<TaskHistoryEntry[]> => getEnvelope<TaskHistoryEntry[]>(routes.taskHistory);
export const getHardwareState = (): Promise<HardwareState> => getEnvelope<HardwareState>(routes.hardwareState);
export const getVisionTargets = (): Promise<VisionTarget[]> => getEnvelope<VisionTarget[]>(routes.visionTargets);
export const getVisionFrame = (): Promise<VisionFrame> => getEnvelope<VisionFrame>(routes.visionFrame);
export const getCalibrationProfile = (): Promise<CalibrationProfile> => getEnvelope<CalibrationProfile>(routes.calibrationProfile);
export const getCalibrationVersions = (): Promise<CalibrationProfileVersion[]> => getEnvelope<CalibrationProfileVersion[]>(routes.calibrationProfiles);
export const getDiagnosticsSummary = (): Promise<DiagnosticsSummary> => getEnvelope<DiagnosticsSummary>(routes.diagnosticsSummary);
export const getLogEvents = (): Promise<LogEvent[]> => getEnvelope<LogEvent[]>(routes.logsEvents);
export const getAuditLogRecords = (): Promise<CommandAuditRecord[]> => getEnvelope<CommandAuditRecord[]>(routes.logsAudit);
export const getCommandReceiptRecords = (): Promise<CommandReceiptRecord[]> => getEnvelope<CommandReceiptRecord[]>(routes.logsReceipts);

export async function putCalibrationProfile(profile: CalibrationProfile): Promise<void> {
  await putEnvelope<null>(routes.calibrationProfile, profile);
}

export async function activateCalibrationProfileVersion(profileId: string): Promise<void> {
  await putEnvelope<null>(`/api/calibration/profiles/${encodeURIComponent(profileId)}/activate`);
}

export async function clearVisionTargetSet(): Promise<void> {
  await postEnvelope<null>(routes.visionClearTargets);
}

export function startTask(payload: StartTaskRequest = {}): Promise<StartTaskDecision> {
  return postEnvelope<StartTaskDecision>(routes.taskStart, payload);
}

export function stopTaskCommand(): Promise<CommandTransportResult> {
  return postEnvelope<CommandTransportResult>(routes.taskStop);
}

export function homeRobotCommand(): Promise<CommandTransportResult> {
  return postEnvelope<CommandTransportResult>(routes.systemHome);
}

export function resetFaultCommand(): Promise<CommandTransportResult> {
  return postEnvelope<CommandTransportResult>(routes.systemResetFault);
}

export function recoverRuntimeCommand(): Promise<CommandTransportResult> {
  return postEnvelope<CommandTransportResult>(routes.systemRecover);
}

export function emergencyStopCommand(): Promise<CommandTransportResult> {
  return postEnvelope<CommandTransportResult>(routes.systemEmergencyStop);
}

export function setHardwareMode(payload: { mode: string }): Promise<CommandTransportResult> {
  return postEnvelope<CommandTransportResult>(routes.hardwareSetMode, payload);
}

export function commandHardwareGripper(payload: { open: boolean }): Promise<CommandTransportResult> {
  return postEnvelope<CommandTransportResult>(routes.hardwareGripper, payload);
}

export function jogHardwareJoint(payload: { jointIndex: number; direction: -1 | 1; stepDeg: number }): Promise<CommandTransportResult> {
  return postEnvelope<CommandTransportResult>(routes.hardwareJogJoint, payload);
}

export function servoHardwareCartesian(payload: { axis: string; delta: number }): Promise<CommandTransportResult> {
  return postEnvelope<CommandTransportResult>(routes.hardwareServoCartesian, payload);
}
