import { defineStore } from 'pinia';
import type { HardwareState } from '@/models/robot';
import type { ControllerMode } from '@/models/system';
import { commandGripper, jogJoint, servoCartesian, setControllerMode } from '@/services/api/hardware';
import { useSafetyStore } from '@/stores/safety';
import { useAppStore } from '@/stores/app';
import { useAuditStore } from '@/stores/audit';
import { invalidateResources } from '@/shared/runtime/invalidation';

export const useRobotStore = defineStore('robot', {
  state: (): { hardware: HardwareState | null; loading: boolean; pendingCommand: boolean; lastCommandAt: string; lastCommand: string } => ({
    hardware: null,
    loading: false,
    pendingCommand: false,
    lastCommandAt: '',
    lastCommand: ''
  }),
  getters: {
    hasJointLimit(state): boolean {
      return Boolean(state.hardware?.limits.some(Boolean));
    }
  },
  actions: {
    setHardwareState(payload: HardwareState) { this.hardware = payload; },
    async setGripper(open: boolean) {
      if (this.pendingCommand) return;
      const safetyStore = useSafetyStore(); const appStore = useAppStore(); const auditStore = useAuditStore();
      if (!safetyStore.canControlGripper.allowed) { auditStore.recordBlocked('hardware.gripper', appStore.operatorRole, safetyStore.canControlGripper.reason, { open }, safetyStore.guardSummary); throw new Error(safetyStore.canControlGripper.reason); }
      this.pendingCommand = true;
      this.lastCommand = open ? 'gripper.open' : 'gripper.close';
      this.lastCommandAt = new Date().toISOString();
      const audit = auditStore.createEntry({ action: this.lastCommand, actorRole: appStore.operatorRole, reason: '夹爪命令已受理', payload: { open }, guardSummary: safetyStore.guardSummary });
      try { await commandGripper(open); if (this.hardware) this.hardware.gripperOpen = open; auditStore.updateStatus(audit.id, 'success', '夹爪命令发送成功'); invalidateResources(['hardware', 'logs', 'audit']); }
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
      try { await jogJoint(jointIndex, direction, stepDeg); auditStore.updateStatus(audit.id, 'success', '点动命令发送成功'); invalidateResources(['hardware', 'logs', 'audit']); }
      catch (error) { auditStore.updateStatus(audit.id, 'failed', error instanceof Error ? error.message : '点动失败'); throw error; }
      finally { this.pendingCommand = false; }
    },
    async servo(axis: string, delta: number) {
      if (this.pendingCommand) return;
      const safetyStore = useSafetyStore(); const appStore = useAppStore(); const auditStore = useAuditStore();
      const backendServoPolicy = safetyStore.snapshot.commandPolicies?.servoCartesian;
      if (backendServoPolicy && !backendServoPolicy.allowed) {
        auditStore.recordBlocked('hardware.servo_cartesian', appStore.operatorRole, backendServoPolicy.reason, { axis, delta }, safetyStore.guardSummary);
        throw new Error(backendServoPolicy.reason);
      }
      if (!safetyStore.canJog.allowed) { auditStore.recordBlocked('hardware.servo_cartesian', appStore.operatorRole, safetyStore.canJog.reason, { axis, delta }, safetyStore.guardSummary); throw new Error(safetyStore.canJog.reason); }
      this.pendingCommand = true;
      this.lastCommand = `servo.${axis}`;
      this.lastCommandAt = new Date().toISOString();
      const audit = auditStore.createEntry({ action: this.lastCommand, actorRole: appStore.operatorRole, reason: '笛卡尔伺服命令已受理', payload: { axis, delta }, guardSummary: safetyStore.guardSummary });
      try { await servoCartesian(axis, delta); auditStore.updateStatus(audit.id, 'success', '笛卡尔伺服命令发送成功'); invalidateResources(['hardware', 'logs', 'audit']); }
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
      try { await setControllerMode(mode); auditStore.updateStatus(audit.id, 'success', '控制器模式切换命令发送成功'); invalidateResources(['system', 'hardware', 'logs', 'audit', 'readiness']); }
      catch (error) { auditStore.updateStatus(audit.id, 'failed', error instanceof Error ? error.message : '控制器模式切换失败'); throw error; }
      finally { this.pendingCommand = false; }
    }
  }
});
