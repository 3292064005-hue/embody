import type { HardwareState } from '@/models/robot';
import type { ControllerMode } from '@/models/system';
import {
  commandHardwareGripper,
  getHardwareState,
  jogHardwareJoint,
  servoHardwareCartesian,
  setHardwareMode,
  type CommandTransportResult as GeneratedCommandTransportResult,
} from '@/api/generated';

export interface HardwareCommandResult extends GeneratedCommandTransportResult {}

export async function fetchHardwareState(): Promise<HardwareState> {
  return getHardwareState();
}

export async function commandGripper(open: boolean): Promise<HardwareCommandResult> {
  return commandHardwareGripper({ open });
}

export async function jogJoint(jointIndex: number, direction: -1 | 1, stepDeg: number): Promise<HardwareCommandResult> {
  return jogHardwareJoint({ jointIndex, direction, stepDeg });
}

export async function servoCartesian(axis: string, delta: number): Promise<HardwareCommandResult> {
  return servoHardwareCartesian({ axis, delta });
}

export async function setControllerMode(mode: ControllerMode): Promise<HardwareCommandResult> {
  return setHardwareMode({ mode });
}
