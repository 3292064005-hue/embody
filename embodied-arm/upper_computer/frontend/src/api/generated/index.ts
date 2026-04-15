import type { ApiResponse } from '@/models/api';
import { ApiClientError } from '@/models/api';
import { apiClient, unwrapResponse } from '@/services/api/client';

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

export type StartTaskDecision = {
  taskId: string;
  taskRunId: string;
  episodeId: string;
  templateId: string;
  pluginKey: string;
  graphKey: string;
  runtimeTier: 'preview' | 'validated_sim' | 'validated_live';
  productLine: string;
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
  systemReadiness: '/api/system/readiness',
  taskStart: '/api/task/start',
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

export async function fetchSystemReadiness(): Promise<RuntimeReadiness> {
  try {
    return await unwrapResponse<RuntimeReadiness>(apiClient.get<ApiResponse<RuntimeReadiness>>(routes.systemReadiness));
  } catch (error) {
    throw asRuntimeApiError(error);
  }
}

export async function startTask(payload: StartTaskRequest = {}): Promise<StartTaskDecision> {
  try {
    return await unwrapResponse<StartTaskDecision>(apiClient.post<ApiResponse<StartTaskDecision>>(routes.taskStart, payload));
  } catch (error) {
    throw asRuntimeApiError(error);
  }
}
