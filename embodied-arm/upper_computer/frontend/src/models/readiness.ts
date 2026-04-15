
export interface RuntimeReleaseGates {
  repoGate: string;
  targetGate: string;
  hilGate: string;
  releaseChecklistGate: string;
  releaseGate: string;
  hasBlockingStep?: boolean;
  blockingSteps?: Record<string, string>;
}

export interface RuntimePromotionReceipt {
  promotion_mode?: string;
  promoted: boolean;
  receipt_id?: string;
  checked_by?: string;
  checked_at?: string;
  required_evidence?: string[];
  evidence?: string[];
  reason?: string;
  effective?: boolean;
  missing_evidence?: string[];
  auto_generated?: boolean;
}

export interface ExecutionBackboneSummary {
  runtimeDeliveryTrack: string;
  executionBackbone: string;
  executionMode: string;
  executionModeLabel?: string;
  authoritativeTransport: boolean;
  sequentialDispatch: boolean;
  requestedRuntimeProfile?: string;
  activeRuntimeLane?: string;
  backboneLabel?: string;
  declaredByRuntimeProfile?: boolean;
  firmwareProfile?: string;
  firmwareMessage?: string;
}

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

export interface ManualCommandLimits {
  maxServoCartesianDeltaMeters: number;
  maxJogJointStepDeg: number;
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
  runtimeTier?: 'preview' | 'validated_sim' | 'validated_live';
  productLine?: string;
  runtimeDeliveryTrack?: string;
  executionBackbone?: string;
  executionBackboneSummary?: ExecutionBackboneSummary;
  promotionReceipts?: Record<string, RuntimePromotionReceipt>;
  releaseGates?: RuntimeReleaseGates;
  firmwareSemanticProfile?: string;
  firmwareSemanticMessage?: string;
  manualCommandLimits?: ManualCommandLimits;
  runtimeConfigVersion?: string;
  updatedAt?: string;
}
