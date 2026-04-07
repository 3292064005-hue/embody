export interface ObservabilitySummary {
  queueDepth: number;
  droppedRecords: number;
  strictSync: boolean;
  lastFlushAt?: string | null;
  lastFlushDurationMs?: number | null;
  lastFsyncDurationMs?: number | null;
  lastError?: string | null;
}

export interface DiagnosticsSummary {
  ready: boolean;
  latencyMs?: number | null;
  taskSuccessRate?: number | null;
  faultCount: number;
  degraded: boolean;
  detail: string;
  updatedAt: string;
  observability?: ObservabilitySummary;
}
