import { defineStore } from 'pinia';
import type { DiagnosticsSummary } from '@/models/diagnostics';

const defaultDiagnostics: DiagnosticsSummary = {
  ready: false,
  latencyMs: null,
  taskSuccessRate: null,
  faultCount: 0,
  degraded: true,
  detail: 'waiting_for_runtime',
  updatedAt: '',
  observability: {
    queueDepth: 0,
    droppedRecords: 0,
    strictSync: false,
    lastFlushAt: null,
    lastFlushDurationMs: null,
    lastFsyncDurationMs: null,
    lastError: null,
  }
};

export const useDiagnosticsStore = defineStore('diagnostics', {
  state: (): DiagnosticsSummary => ({ ...defaultDiagnostics }),
  actions: {
    setSummary(payload: DiagnosticsSummary) {
      this.ready = payload.ready;
      this.latencyMs = payload.latencyMs ?? null;
      this.taskSuccessRate = payload.taskSuccessRate ?? null;
      this.faultCount = payload.faultCount;
      this.degraded = payload.degraded;
      this.detail = payload.detail;
      this.updatedAt = payload.updatedAt;
      this.observability = payload.observability || { ...defaultDiagnostics.observability! };
    }
  }
});
