import type { ControllerMode } from '@/models/system';
import type { StartTaskPayload } from '@/models/task';
import type { CalibrationProfile } from '@/models/vision';
import { useRobotStore } from '@/stores/robot';
import { useSystemStore } from '@/stores/system';
import { useTaskStore } from '@/stores/task';
import { useVisionStore } from '@/stores/vision';

export interface CommandBus {
  startTask(payload: StartTaskPayload): Promise<void>;
  stopTask(): Promise<void>;
  home(): Promise<void>;
  resetFault(): Promise<void>;
  emergencyStop(): Promise<void>;
  setControllerMode(mode: ControllerMode): Promise<void>;
  setGripper(open: boolean): Promise<void>;
  jogJoint(jointIndex: number, direction: -1 | 1, stepDeg: number): Promise<void>;
  servoCartesian(axis: string, delta: number): Promise<void>;
  saveCalibration(profile: CalibrationProfile): Promise<void>;
  activateCalibrationProfile(profileId: string): Promise<void>;
}

export function useCommandBus(): CommandBus {
  const taskStore = useTaskStore();
  const systemStore = useSystemStore();
  const robotStore = useRobotStore();
  const visionStore = useVisionStore();

  return {
    async startTask(payload) {
      await taskStore.startTask(payload);
    },
    async stopTask() {
      await taskStore.stopTask();
    },
    async home() {
      await systemStore.homeRobot();
    },
    async resetFault() {
      await systemStore.resetFault();
    },
    async emergencyStop() {
      await systemStore.emergencyStop();
    },
    async setControllerMode(mode) {
      await robotStore.setControllerMode(mode);
    },
    async setGripper(open) {
      await robotStore.setGripper(open);
    },
    async jogJoint(jointIndex, direction, stepDeg) {
      await robotStore.jogJoint(jointIndex, direction, stepDeg);
    },
    async servoCartesian(axis, delta) {
      await robotStore.servo(axis, delta);
    },
    async saveCalibration(profile) {
      await visionStore.saveCalibration(profile);
    },
    async activateCalibrationProfile(profileId) {
      await visionStore.activateProfile(profileId);
    }
  };
}
