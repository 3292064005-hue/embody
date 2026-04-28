import { defineStore } from 'pinia';
import type { CommandTransportResult, CommandDecisionLike } from '@/services/api/commandResult';
import { commandAccepted, commandCompletionPending } from '@/services/api/commandResult';
import type { CommandAuditRecord } from '@/models/audit';
import type { CommandReceiptRecord } from '@/models/receipt';
import type { CommandLifecycleExpectation, CommandLifecyclePhase, CommandLifecycleRecord, CommandLifecycleTerminalStatus } from '@/models/commandLifecycle';
import type { SystemState } from '@/models/system';
import type { TaskProgress } from '@/models/task';
import type { HardwareState } from '@/models/robot';
import { resolveControllerMode } from '@/models/system';

const TERMINAL_STATUSES = new Set<CommandLifecycleTerminalStatus>(['success', 'failed', 'blocked', 'rejected', 'observed']);
const PENDING_TIMEOUT_MS = 10_000;

function lifecycleId(requestId: string, action: string): string {
  return `${action}:${requestId}`;
}

function nowIso(): string {
  return new Date().toISOString();
}

function normalizeTerminalStatus(value: unknown): CommandLifecycleTerminalStatus | null {
  const status = String(value || '').trim().toLowerCase();
  if (status === 'completed') return 'success';
  if (TERMINAL_STATUSES.has(status as CommandLifecycleTerminalStatus)) return status as CommandLifecycleTerminalStatus;
  return null;
}

function isAcceptedStatus(value: unknown): boolean {
  return String(value || '').trim().toLowerCase() === 'accepted';
}

export const useCommandLifecycleStore = defineStore('commandLifecycle', {
  state: (): { records: CommandLifecycleRecord[] } => ({ records: [] }),
  getters: {
    pendingRecords(state): CommandLifecycleRecord[] {
      return state.records.filter((item) => item.status === 'accepted');
    },
    latest(state): CommandLifecycleRecord | null {
      return state.records[0] || null;
    },
    pendingCount(): number {
      return this.pendingRecords.length;
    },
  },
  actions: {
    _upsert(record: CommandLifecycleRecord) {
      this.records = [record, ...this.records.filter((item) => item.id !== record.id)].slice(0, 500);
    },
    registerAccepted(action: string, result: CommandDecisionLike, options: { message: string; payload?: Record<string, unknown>; expectation?: CommandLifecycleExpectation } ) {
      if (!result || !commandAccepted(result)) return;
      const requestId = String(result.requestId || result.operationId || `${action}-${Date.now()}`);
      const completionPending = commandCompletionPending(result);
      const acceptedAt = nowIso();
      const localPreviewOnly = 'localPreviewOnly' in result && typeof result.localPreviewOnly === 'boolean' ? result.localPreviewOnly : false;
      const resultMessage = 'message' in result && typeof result.message === 'string' ? result.message : options.message;
      const record: CommandLifecycleRecord = {
        id: lifecycleId(requestId, action),
        action,
        requestId,
        operationId: result.operationId ? String(result.operationId) : undefined,
        receiptId: result.receiptId ? String(result.receiptId) : undefined,
        acceptedAt,
        updatedAt: acceptedAt,
        finalizedAt: completionPending && !localPreviewOnly ? undefined : acceptedAt,
        status: completionPending && !localPreviewOnly ? 'accepted' : (localPreviewOnly ? 'observed' : 'success'),
        authoritativeStatus: String(result.authoritativeStatus || (completionPending ? 'accepted' : 'success')),
        completionPending,
        localPreviewOnly,
        message: localPreviewOnly ? resultMessage : options.message,
        payload: options.payload,
        expectation: options.expectation,
      };
      this._upsert(record);
      this.sweepTimeouts();
    },
    finalize(requestId: string, status: CommandLifecycleTerminalStatus, message: string, patch: Partial<CommandLifecycleRecord> = {}) {
      const updatedAt = nowIso();
      let changed = false;
      this.records = this.records.map((item) => {
        if (item.requestId !== requestId || item.status !== 'accepted') return item;
        changed = true;
        return {
          ...item,
          ...patch,
          status,
          message,
          completionPending: false,
          updatedAt,
          finalizedAt: updatedAt,
          authoritativeStatus: patch.authoritativeStatus || status,
        };
      });
      if (changed) this.records = [...this.records];
    },
    mergeReceipt(record: Partial<CommandReceiptRecord> | Record<string, unknown>) {
      const requestId = String(record.requestId || '');
      if (!requestId) return;
      const status = normalizeTerminalStatus(record.status);
      const updatedAt = nowIso();
      const receiptId = record.id ? String(record.id) : undefined;
      this.records = this.records.map((item) => {
        if (item.requestId !== requestId) return item;
        if (status) {
          return {
            ...item,
            receiptId: receiptId || item.receiptId,
            updatedAt,
            finalizedAt: updatedAt,
            status,
            completionPending: false,
            authoritativeStatus: status,
            message: String(record.message || item.message),
          };
        }
        if (isAcceptedStatus(record.status)) {
          return {
            ...item,
            receiptId: receiptId || item.receiptId,
            updatedAt,
            authoritativeStatus: 'accepted',
            message: String(record.message || item.message),
          };
        }
        return item;
      });
      this.sweepTimeouts();
    },
    mergeAudit(record: Partial<CommandAuditRecord> | Record<string, unknown>) {
      const requestId = String(record.requestId || '');
      if (!requestId) return;
      const status = normalizeTerminalStatus(record.status);
      if (!status) return;
      const message = 'reason' in record && typeof record.reason === 'string'
        ? record.reason
        : ('message' in record && typeof record.message === 'string' ? record.message : status);
      this.finalize(requestId, status, String(message), {
        authoritativeStatus: status,
      });
    },
    reconcileTask(task: TaskProgress | null) {
      for (const item of this.pendingRecords) {
        if (item.action === 'task.start' && item.expectation?.taskId && task?.taskId === item.expectation.taskId) {
          this.finalize(item.requestId, 'success', `任务已进入权威运行态（taskId=${task.taskId}）`);
        } else if (item.action === 'task.stop' && task === null) {
          this.finalize(item.requestId, 'success', '停止任务已由权威运行时确认');
        }
      }
      this.sweepTimeouts();
    },
    reconcileSystem(system: SystemState | null) {
      if (!system) return;
      const controllerMode = resolveControllerMode(system as unknown as Record<string, unknown>);
      for (const item of this.pendingRecords) {
        if (item.action === 'system.reset_fault' && system.runtimePhase !== 'fault') {
          this.finalize(item.requestId, 'success', '故障复位已由权威系统状态确认');
        } else if (item.action === 'system.recover' && system.runtimePhase === 'idle') {
          this.finalize(item.requestId, 'success', '运行时恢复已由权威系统状态确认');
        } else if (item.action === 'system.emergency_stop' && (system.emergencyStop || system.runtimePhase === 'safe_stop')) {
          this.finalize(item.requestId, 'success', '急停已由权威系统状态确认');
        } else if (item.action === 'hardware.set_mode' && item.expectation?.controllerMode && controllerMode === item.expectation.controllerMode) {
          this.finalize(item.requestId, 'success', `控制器模式已切换为 ${controllerMode}`);
        } else if (item.action === 'task.start' && item.expectation?.taskId && system.currentTaskId === item.expectation.taskId) {
          this.finalize(item.requestId, 'success', `任务已由权威系统状态绑定（taskId=${system.currentTaskId}）`);
        } else if (item.action === 'task.stop' && !system.currentTaskId) {
          this.finalize(item.requestId, 'success', '停止任务已由权威系统状态确认');
        }
      }
      this.sweepTimeouts();
    },
    reconcileHardware(hardware: HardwareState | null) {
      if (!hardware) return;
      for (const item of this.pendingRecords) {
        if (item.action === 'system.home' && hardware.homed) {
          this.finalize(item.requestId, 'success', '回零完成已由权威硬件状态确认');
        } else if (item.action === 'hardware.gripper' && typeof item.expectation?.gripperOpen === 'boolean' && hardware.gripperOpen === item.expectation.gripperOpen) {
          this.finalize(item.requestId, 'success', `夹爪状态已更新为${hardware.gripperOpen ? '打开' : '闭合'}`);
        }
      }
      this.sweepTimeouts();
    },
    sweepTimeouts(nowMs: number = Date.now()) {
      this.records = this.records.map((item) => {
        if (item.status !== 'accepted') return item;
        const acceptedAt = Date.parse(item.acceptedAt);
        if (!Number.isFinite(acceptedAt) || nowMs - acceptedAt < PENDING_TIMEOUT_MS) return item;
        return {
          ...item,
          status: 'observed',
          completionPending: false,
          authoritativeStatus: 'observed',
          updatedAt: new Date(nowMs).toISOString(),
          finalizedAt: new Date(nowMs).toISOString(),
          message: `${item.message}；在超时时间内未收到终态回执，请以后端日志/回执为准。`,
        };
      });
    },
  },
});
