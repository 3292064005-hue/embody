import { defineStore } from 'pinia';
import type { CommandReceiptRecord } from '@/models/receipt';
import { useCommandLifecycleStore } from '@/stores/commandLifecycle';

function normalizeReceipt(raw: Partial<CommandReceiptRecord> | Record<string, unknown>): CommandReceiptRecord {
  return {
    id: String(raw.id || `receipt-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`),
    timestamp: String(raw.timestamp || new Date().toISOString()),
    action: String(raw.action || 'unknown'),
    status: String(raw.status || 'observed'),
    role: String(raw.role || 'system'),
    requestId: String(raw.requestId || ''),
    correlationId: raw.correlationId ? String(raw.correlationId) : undefined,
    commandPlane: String(raw.commandPlane || 'system_control'),
    receiptClass: String(raw.receiptClass || 'observability_event'),
    executionBound: Boolean(raw.executionBound),
    errorCode: raw.errorCode ? String(raw.errorCode) : undefined,
    operatorActionable: typeof raw.operatorActionable === 'boolean' ? raw.operatorActionable : undefined,
    message: String(raw.message || ''),
    payload: (raw.payload as Record<string, unknown> | undefined) || undefined,
  };
}

export const useReceiptStore = defineStore('receipt', {
  state: (): { records: CommandReceiptRecord[] } => ({ records: [] }),
  getters: {
    latest(state): CommandReceiptRecord | null {
      return state.records[0] || null;
    },
  },
  actions: {
    setRecords(records: Array<Partial<CommandReceiptRecord> | Record<string, unknown>>) {
      const normalized = records.map(normalizeReceipt).slice(0, 500);
      this.records = normalized;
      const lifecycleStore = useCommandLifecycleStore();
      normalized.forEach((item) => lifecycleStore.mergeReceipt(item));
    },
    mergeServerRecord(record: Partial<CommandReceiptRecord> | Record<string, unknown>) {
      const normalized = normalizeReceipt(record);
      this.records = [normalized, ...this.records.filter((item) => item.id !== normalized.id)].slice(0, 500);
      useCommandLifecycleStore().mergeReceipt(normalized);
    },
  },
});
