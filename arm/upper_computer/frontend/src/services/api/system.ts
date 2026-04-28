import type { SystemState } from '@/models/system';
import type { ReadinessState } from '@/models/readiness';
import {
  emergencyStopCommand,
  fetchSystemReadiness,
  homeRobotCommand,
  recoverRuntimeCommand,
  resetFaultCommand,
  type CommandTransportResult as GeneratedCommandTransportResult,
} from '@/api/generated';
import { apiClient, unwrapResponse } from './client';

export async function fetchSystemSummary(): Promise<SystemState> {
  return unwrapResponse(apiClient.get('/api/system/summary'));
}

export async function fetchReadiness(): Promise<ReadinessState> {
  return fetchSystemReadiness();
}

export interface SystemCommandResult extends GeneratedCommandTransportResult {}

export async function homeRobot(): Promise<SystemCommandResult> {
  return homeRobotCommand();
}

export async function resetFault(): Promise<SystemCommandResult> {
  return resetFaultCommand();
}

export async function recoverRuntime(): Promise<SystemCommandResult> {
  return recoverRuntimeCommand();
}

export async function emergencyStop(): Promise<SystemCommandResult> {
  return emergencyStopCommand();
}
