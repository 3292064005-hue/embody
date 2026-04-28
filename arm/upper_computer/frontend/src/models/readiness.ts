
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
  declaredExecutionBackbone?: string;
  declaredExecutionMode?: string;
  effectiveExecutionBackbone?: string;
  effectiveExecutionMode?: string;
  executionModeLabel?: string;
  authoritativeTransport: boolean;
  effectiveTransportReady?: boolean;
  sequentialDispatch: boolean;
  requestedRuntimeProfile?: string;
  activeRuntimeLane?: string;
  backboneLabel?: string;
  effectiveBackboneLabel?: string;
  effectiveExecutionModeLabel?: string;
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


export interface RuntimeFeatureState {
  authoritativeRuntime: boolean;
  previewRuntime: boolean;
  runtimeTier: 'preview' | 'validated_sim' | 'validated_live';
  runtimeLabel: string;
  runtimeBadge: string;
  promotionControlled: boolean;
  promotionEffective: boolean;
  promotionMissing: string[];
  taskWorkbenchVisible: boolean;
  taskExecutionInteractive: boolean;
  taskStartReason: string;
}

export interface RuntimeCapabilityDescriptor {
  data_plane: string;
  control_plane: string;
  execution_binding: string;
  authority_level: string;
}

export interface RuntimeCommandPlaneContract {
  entrypoint: string;
  release_track: string;
  producer: string;
  allowed_roles: string[];
  dispatch_mode: string;
  receipt_class: string;
  runtime_interface?: string;
  audit_required: boolean;
}


export interface AuthorityState {
  level: string;
  authoritativeRuntime: boolean;
  authoritativeTransport: boolean;
  localPreview: boolean;
  bootstrap: boolean;
  maintenanceCommandReady: boolean;
  detail: string;
}

export interface CommandSurfaceState {
  surface: string;
  interactive: boolean;
  allowedCommands: string[];
  blockedCommands: string[];
  readyCount: number;
  blockedCount: number;
  startTaskAllowed: boolean;
  detail: string;
}

export interface TaskExecutionState {
  workbenchVisible: boolean;
  interactive: boolean;
  startAllowed: boolean;
  runtimeTier: 'preview' | 'validated_sim' | 'validated_live';
  reason: string;
  promotionControlled: boolean;
  promotionEffective: boolean;
  promotionMissing: string[];
  startMissingChecks?: string[];
  startMissingDetails?: Array<{ name: string; detail: string }>;
}

export interface RuntimeSurfaceState {
  runtimeTier: 'preview' | 'validated_sim' | 'validated_live';
  runtimeBadge: string;
  runtimeLabel: string;
  taskWorkbenchVisible: boolean;
  taskExecutionInteractive: boolean;
  runtimeDeliveryTrack: string;
  executionBackbone: string;
  declaredExecutionBackbone?: string;
  effectiveExecutionBackbone?: string;
  publicCommandPlanes: string[];
  observabilityCommandPlanes: string[];
  runtimeGatewayEntrypoints: string[];
  activeRuntimeInterfaces: string[];
  hiddenRuntimeInterfaces: string[];
  capabilityDescriptorKeys: string[];
  authorityState?: AuthorityState;
  commandSurfaceState?: CommandSurfaceState;
  taskExecutionState?: TaskExecutionState;
  runtimeFingerprint?: string;
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
  commandPlanes?: Record<string, RuntimeCommandPlaneContract>;
  capabilityDescriptors?: Record<string, RuntimeCapabilityDescriptor>;
  runtimeFeatureState?: RuntimeFeatureState;
  authorityState?: AuthorityState;
  commandSurfaceState?: CommandSurfaceState;
  taskExecutionState?: TaskExecutionState;
  runtimeFingerprint?: string;
  runtimeSurfaceState?: RuntimeSurfaceState;
  manualCommandLimits?: ManualCommandLimits;
  runtimeConfigVersion?: string;
  updatedAt?: string;
}
