import { defineStore } from 'pinia';
import type { AuditStatus, CommandAuditRecord } from '@/models/audit';
import type { OperatorRole } from '@/models/safety';
import { generateRequestId } from '@/utils/id';

function normalizeActorRole(value: unknown): OperatorRole {
  return value === 'viewer' || value === 'operator' || value === 'maintainer' ? value : 'operator';
}

function normalizeStatus(value: unknown): AuditStatus {
  return ['pending', 'success', 'failed', 'blocked', 'accepted', 'rejected'].includes(String(value))
    ? (value as AuditStatus)
    : 'pending';
}

function normalizeRecord(raw: Partial<CommandAuditRecord> & { [key: string]: unknown }): CommandAuditRecord {
  return {
    id: String(raw.id || `audit-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`),
    requestId: String(raw.requestId || generateRequestId()),
    action: String(raw.action || 'unknown'),
    actorRole: normalizeActorRole(raw.actorRole || raw.actorMode || raw.role),
    createdAt: String(raw.createdAt || raw.timestamp || new Date().toISOString()),
    finishedAt: raw.finishedAt ? String(raw.finishedAt) : undefined,
    status: normalizeStatus(raw.status),
    reason: String(raw.reason || raw.message || ''),
    payload: (raw.payload as Record<string, unknown> | undefined) || undefined,
    guardSummary: raw.guardSummary ? String(raw.guardSummary) : undefined,
    correlationId: raw.correlationId ? String(raw.correlationId) : undefined,
    taskId: raw.taskId ? String(raw.taskId) : undefined
  };
}

export const useAuditStore = defineStore('audit', {
  state: (): { records: CommandAuditRecord[] } => ({ records: [] }),
  getters: {
    latest(state): CommandAuditRecord | null {
      return state.records[0] || null;
    }
  },
  actions: {
    setRecords(records: Array<Partial<CommandAuditRecord> | (Partial<CommandAuditRecord> & { [key: string]: unknown })>) {
      this.records = records.map((record) => normalizeRecord(record as Partial<CommandAuditRecord> & { [key: string]: unknown })).slice(0, 500);
    },
    mergeServerRecord(record: Partial<CommandAuditRecord> | (Partial<CommandAuditRecord> & { [key: string]: unknown })) {
      const normalized = normalizeRecord(record as Partial<CommandAuditRecord> & { [key: string]: unknown });
      this.records = [normalized, ...this.records.filter((item) => item.id !== normalized.id)].slice(0, 500);
    },
    createEntry(payload: { action: string; actorRole: OperatorRole; reason: string; payload?: Record<string, unknown>; guardSummary?: string; requestId?: string; status?: AuditStatus }): CommandAuditRecord {
      const entry = normalizeRecord({
        id: `audit-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        requestId: payload.requestId || generateRequestId(),
        action: payload.action,
        actorRole: payload.actorRole,
        createdAt: new Date().toISOString(),
        status: payload.status || 'pending',
        reason: payload.reason,
        payload: payload.payload,
        guardSummary: payload.guardSummary
      });
      this.records = [entry, ...this.records].slice(0, 500);
      return entry;
    },
    updateStatus(entryId: string, status: AuditStatus, reason: string) {
      this.records = this.records.map((item) => item.id === entryId ? { ...item, status, reason, finishedAt: new Date().toISOString() } : item);
    },
    recordBlocked(action: string, actorRole: OperatorRole, reason: string, payload?: Record<string, unknown>, guardSummary?: string) {
      this.createEntry({ action, actorRole, reason, payload, guardSummary, status: 'blocked' });
    }
  }
});
