export interface ReadinessCheck {
  ok: boolean;
  detail: string;
  effectiveOk?: boolean;
  ageSec?: number;
  stale?: boolean;
  staleAfterSec?: number | null;
}

export interface ReadinessMissingDetail {
  name: string;
  detail: string;
}

export interface ReadinessCommandPolicy {
  allowed: boolean;
  reason: string;
}

export interface CommandSummary {
  allowed: string[];
  blocked: string[];
  readyCount: number;
  blockedCount: number;
}

export interface ReadinessState {
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
  updatedAt?: string;
}
