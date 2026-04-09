import { defineStore } from 'pinia';
import type { RuntimePhase, SystemState } from '@/models/system';
import { coerceSystemState, resolveControllerMode } from '@/models/system';
import { emergencyStop, homeRobot, recoverRuntime, resetFault } from '@/services/api/system';
import { useSafetyStore } from '@/stores/safety';
import { useAppStore } from '@/stores/app';
import { useAuditStore } from '@/stores/audit';
import { invalidateResources } from '@/shared/runtime/invalidation';

function runtimePhaseOf(current: SystemState | null): RuntimePhase {
  return current?.runtimePhase || current?.mode || 'boot';
}

export const useSystemStore = defineStore('system', {
  state: (): { current: SystemState | null; loading: boolean; pendingCommand: boolean } => ({ current: null, loading: false, pendingCommand: false }),
  getters: {
    isFault(state): boolean { return runtimePhaseOf(state.current) === 'fault'; },
    isBusy(state): boolean { return ['execute', 'plan', 'verify', 'perception'].includes(runtimePhaseOf(state.current)); },
    runtimePhase(state): RuntimePhase { return runtimePhaseOf(state.current); },
    controllerMode(state): string { return state.current ? resolveControllerMode(state.current as Record<string, unknown>) : 'idle'; },
    systemTimestamp(state): string { return state.current?.timestamp || ''; }
  },
  actions: {
    setState(payload: SystemState) { this.current = coerceSystemState(payload as Partial<SystemState> & Record<string, unknown>); },
    async homeRobot() {
      if (this.pendingCommand) return;
      const safetyStore = useSafetyStore(); const appStore = useAppStore(); const auditStore = useAuditStore();
      if (!safetyStore.canHomeRobot.allowed) { auditStore.recordBlocked('system.home', appStore.operatorRole, safetyStore.canHomeRobot.reason, undefined, safetyStore.guardSummary); throw new Error(safetyStore.canHomeRobot.reason); }
      this.pendingCommand = true;
      const audit = auditStore.createEntry({ action: 'system.home', actorRole: appStore.operatorRole, reason: '回零命令已受理', guardSummary: safetyStore.guardSummary });
      try { await homeRobot(); auditStore.updateStatus(audit.id, 'success', '回零命令发送成功'); invalidateResources(['system', 'hardware', 'logs']); }
      catch (error) { auditStore.updateStatus(audit.id, 'failed', error instanceof Error ? error.message : '回零失败'); throw error; }
      finally { this.pendingCommand = false; }
    },
    async resetFault() {
      if (this.pendingCommand) return;
      const safetyStore = useSafetyStore(); const appStore = useAppStore(); const auditStore = useAuditStore();
      if (!safetyStore.canResetFault.allowed) { auditStore.recordBlocked('system.reset_fault', appStore.operatorRole, safetyStore.canResetFault.reason, undefined, safetyStore.guardSummary); throw new Error(safetyStore.canResetFault.reason); }
      this.pendingCommand = true;
      const audit = auditStore.createEntry({ action: 'system.reset_fault', actorRole: appStore.operatorRole, reason: '故障复位命令已受理', guardSummary: safetyStore.guardSummary });
      try { await resetFault(); auditStore.updateStatus(audit.id, 'success', '故障复位命令发送成功'); invalidateResources(['system', 'hardware', 'logs', 'task.current']); }
      catch (error) { auditStore.updateStatus(audit.id, 'failed', error instanceof Error ? error.message : '故障复位失败'); throw error; }
      finally { this.pendingCommand = false; }
    },
    async recoverRuntime() {
      if (this.pendingCommand) return;
      const safetyStore = useSafetyStore(); const appStore = useAppStore(); const auditStore = useAuditStore();
      if (!safetyStore.canRecover.allowed) { auditStore.recordBlocked('system.recover', appStore.operatorRole, safetyStore.canRecover.reason, undefined, safetyStore.guardSummary); throw new Error(safetyStore.canRecover.reason); }
      this.pendingCommand = true;
      const audit = auditStore.createEntry({ action: 'system.recover', actorRole: appStore.operatorRole, reason: '运行时恢复命令已受理', guardSummary: safetyStore.guardSummary });
      try { await recoverRuntime(); auditStore.updateStatus(audit.id, 'success', '运行时恢复命令发送成功'); invalidateResources(['system', 'hardware', 'logs', 'task.current', 'readiness']); }
      catch (error) { auditStore.updateStatus(audit.id, 'failed', error instanceof Error ? error.message : '运行时恢复失败'); throw error; }
      finally { this.pendingCommand = false; }
    },
    async emergencyStop() {
      if (this.pendingCommand) return;
      const appStore = useAppStore(); const safetyStore = useSafetyStore(); const auditStore = useAuditStore();
      this.pendingCommand = true;
      const audit = auditStore.createEntry({ action: 'system.emergency_stop', actorRole: appStore.operatorRole, reason: '急停命令已受理', guardSummary: safetyStore.guardSummary });
      try { await emergencyStop(); auditStore.updateStatus(audit.id, 'success', '急停命令发送成功'); invalidateResources(['system', 'hardware', 'logs', 'task.current']); }
      catch (error) { auditStore.updateStatus(audit.id, 'failed', error instanceof Error ? error.message : '急停失败'); throw error; }
      finally { this.pendingCommand = false; }
    }
  }
});
