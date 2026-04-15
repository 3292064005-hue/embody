import type { HardwareState } from '@/models/robot';
import type { ControllerMode } from '@/models/system';
import type { CommandTransportResult } from './commandResult';
import { unwrapResponse, apiClient } from './client';

export interface HardwareCommandResult extends CommandTransportResult {}

export async function fetchHardwareState(): Promise<HardwareState> {
  return unwrapResponse(apiClient.get('/api/hardware/state'));
}

export async function commandGripper(open: boolean): Promise<HardwareCommandResult> {
  return unwrapResponse(apiClient.post('/api/hardware/gripper', { open }));
}

export async function jogJoint(jointIndex: number, direction: -1 | 1, stepDeg: number): Promise<HardwareCommandResult> {
  return unwrapResponse(apiClient.post('/api/hardware/jog-joint', { jointIndex, direction, stepDeg }));
}

export async function servoCartesian(axis: string, delta: number): Promise<HardwareCommandResult> {
  return unwrapResponse(apiClient.post('/api/hardware/servo-cartesian', { axis, delta }));
}

export async function setControllerMode(mode: ControllerMode): Promise<HardwareCommandResult> {
  return unwrapResponse(apiClient.post('/api/hardware/set-mode', { mode }));
}
