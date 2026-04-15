import { defineStore } from 'pinia';
import type { HardwareState } from '@/models/robot';
import type { ControllerMode } from '@/models/system';
import { commandGripper, jogJoint, servoCartesian, setControllerMode } from '@/services/api/hardware';
import { useSafetyStore } from '@/stores/safety';
import { useAppStore } from '@/stores/app';
import { useAuditStore } from '@/stores/audit';
import { invalidateResources } from '@/shared/runtime/invalidation';

export const useRobotStore = defineStore('robot', {
  state: (): { hardware: HardwareState | null; loading: boolean; pendingCommand: boolean; lastCommandAt: string; lastCommand: string; localPreviewOnly: boolean; localPreviewMessage: string } => ({
    hardware: null,
    loading: false,
    pendingCommand: false,
    lastCommandAt: '',
    lastCommand: '',
    localPreviewOnly: false,
    localPreviewMessage: ''
  }),
  getters: {
    hasJointLimit(state): boolean {
      return Boolean(state.hardware?.limits.some(Boolean));
    }
  },
  actions: {
    setHardwareState(payload: HardwareState) { this.hardware = payload; },
    applyCommandTransportResult(result?: { localPreviewOnly?: boolean; message?: string }) {
      this.localPreviewOnly = Boolean(result?.localPreviewOnly);
      this.localPreviewMessage = this.localPreviewOnly ? String(result?.message || '当前命令仅做本地 preview 投影，未下发到权威运行时。') : '';
    },
    async setGripper(open: boolean) {
      if (this.pendingCommand) return;
      const safetyStore = useSafetyStore(); const appStore = useAppStore(); const auditStore = useAuditStore();
      if (!safetyStore.canControlGripper.allowed) { auditStore.recordBlocked('hardware.gripper', appStore.operatorRole, safetyStore.canControlGripper.reason, { open }, safetyStore.guardSummary); throw new Error(safetyStore.canControlGripper.reason); }
      this.pendingCommand = true;
      this.lastCommand = open ? 'gripper.open' : 'gripper.close';
      this.lastCommandAt = new Date().toISOString();
      const audit = auditStore.createEntry({ action: this.lastCommand, actorRole: appStore.operatorRole, reason: '夹爪命令已受理', payload: { open }, guardSummary: safetyStore.guardSummary });
      try { const result = await commandGripper(open); this.applyCommandTransportResult(result); if (this.hardware) this.hardware.gripperOpen = open; auditStore.updateStatus(audit.id, 'success', this.localPreviewOnly ? '夹爪命令已进入本地 preview 投影' : '夹爪命令发送成功'); invalidateResources(['hardware', 'logs', 'audit']); }
      catch (error) { auditStore.updateStatus(audit.id, 'failed', error instanceof Error ? error.message : '夹爪控制失败'); throw error; }
      finally { this.pendingCommand = false; }
    },
    async jogJoint(jointIndex: number, direction: -1 | 1, stepDeg: number) {
      if (this.pendingCommand) return;
      const safetyStore = useSafetyStore(); const appStore = useAppStore(); const auditStore = useAuditStore();
      if (!safetyStore.canJog.allowed) { auditStore.recordBlocked('hardware.jog_joint', appStore.operatorRole, safetyStore.canJog.reason, { jointIndex, direction, stepDeg }, safetyStore.guardSummary); throw new Error(safetyStore.canJog.reason); }
      this.pendingCommand = true;
      this.lastCommand = `jog.j${jointIndex + 1}.${direction > 0 ? 'positive' : 'negative'}`;
      this.lastCommandAt = new Date().toISOString();
      const audit = auditStore.createEntry({ action: this.lastCommand, actorRole: appStore.operatorRole, reason: '点动命令已受理', payload: { jointIndex, direction, stepDeg }, guardSummary: safetyStore.guardSummary });
      try { const result = await jogJoint(jointIndex, direction, stepDeg); this.applyCommandTransportResult(result); auditStore.updateStatus(audit.id, 'success', this.localPreviewOnly ? '点动命令已进入本地 preview 投影' : '点动命令发送成功'); invalidateResources(['hardware', 'logs', 'audit']); }
      catch (error) { auditStore.updateStatus(audit.id, 'failed', error instanceof Error ? error.message : '点动失败'); throw error; }
      finally { this.pendingCommand = false; }
    },
    async servo(axis: string, delta: number) {
      if (this.pendingCommand) return;
      const safetyStore = useSafetyStore(); const appStore = useAppStore(); const auditStore = useAuditStore();
      if (!safetyStore.canServoCartesian.allowed) { auditStore.recordBlocked('hardware.servo_cartesian', appStore.operatorRole, safetyStore.canServoCartesian.reason, { axis, delta }, safetyStore.guardSummary); throw new Error(safetyStore.canServoCartesian.reason); }
      this.pendingCommand = true;
      this.lastCommand = `servo.${axis}`;
      this.lastCommandAt = new Date().toISOString();
      const audit = auditStore.createEntry({ action: this.lastCommand, actorRole: appStore.operatorRole, reason: '笛卡尔伺服命令已受理', payload: { axis, delta }, guardSummary: safetyStore.guardSummary });
      try { const result = await servoCartesian(axis, delta); this.applyCommandTransportResult(result); auditStore.updateStatus(audit.id, 'success', this.localPreviewOnly ? '笛卡尔伺服命令已进入本地 preview 投影' : '笛卡尔伺服命令发送成功'); invalidateResources(['hardware', 'logs', 'audit']); }
      catch (error) { auditStore.updateStatus(audit.id, 'failed', error instanceof Error ? error.message : '笛卡尔伺服失败'); throw error; }
      finally { this.pendingCommand = false; }
    },
    async setControllerMode(mode: ControllerMode) {
      if (this.pendingCommand) return;
      const appStore = useAppStore(); const auditStore = useAuditStore();
      this.pendingCommand = true;
      this.lastCommand = `controller_mode.${mode}`;
      this.lastCommandAt = new Date().toISOString();
      const audit = auditStore.createEntry({ action: this.lastCommand, actorRole: appStore.operatorRole, reason: '控制器模式切换命令已受理', payload: { mode } });
      try { const result = await setControllerMode(mode); this.applyCommandTransportResult(result); auditStore.updateStatus(audit.id, 'success', this.localPreviewOnly ? '控制器模式切换仅进入本地 preview 投影' : '控制器模式切换命令发送成功'); invalidateResources(['system', 'hardware', 'logs', 'audit', 'readiness']); }
      catch (error) { auditStore.updateStatus(audit.id, 'failed', error instanceof Error ? error.message : '控制器模式切换失败'); throw error; }
      finally { this.pendingCommand = false; }
    }
  }
});
