import type { ReadinessCommandPolicy, RuntimeCommandPlaneContract } from '@/models/readiness';

export type OperatorRole = 'viewer' | 'operator' | 'maintainer';

export interface GuardDecision {
  allowed: boolean;
  reason: string;
}

export interface SafetySnapshot {
  operatorRole: OperatorRole;
  gatewayConnected: boolean;
  realtimeStale: boolean;
  emergencyStop: boolean;
  faultMode: boolean;
  systemBusy: boolean;
  hardwareBusy: boolean;
  homed: boolean;
  readonlyDegraded: boolean;
  commandPolicies?: Record<string, ReadinessCommandPolicy>;
  commandPlanes?: Record<string, RuntimeCommandPlaneContract>;
}
