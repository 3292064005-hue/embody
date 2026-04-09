import type { HardwareState } from '@/models/robot';
import type { ControllerMode } from '@/models/system';
import { unwrapResponse, apiClient, postVoid } from './client';

export async function fetchHardwareState(): Promise<HardwareState> {
  return unwrapResponse(apiClient.get('/api/hardware/state'));
}

export async function commandGripper(open: boolean): Promise<void> {
  await postVoid('/api/hardware/gripper', { open });
}

export async function jogJoint(jointIndex: number, direction: -1 | 1, stepDeg: number): Promise<void> {
  await postVoid('/api/hardware/jog-joint', { jointIndex, direction, stepDeg });
}

export async function servoCartesian(axis: string, delta: number): Promise<void> {
  await postVoid('/api/hardware/servo-cartesian', { axis, delta });
}

export async function setControllerMode(mode: ControllerMode): Promise<void> {
  await postVoid('/api/hardware/set-mode', { mode });
}
