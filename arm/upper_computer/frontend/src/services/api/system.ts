import type { SystemState } from '@/models/system';
import type { ReadinessState } from '@/models/readiness';
import {
  emergencyStopCommand,
  fetchSystemReadiness,
  getSystemSummary,
  homeRobotCommand,
  recoverRuntimeCommand,
  resetFaultCommand,
  type CommandTransportResult as GeneratedCommandTransportResult,
} from '@/api/generated';

export async function fetchSystemSummary(): Promise<SystemState> {
  return getSystemSummary();
}

export async function fetchReadiness(): Promise<ReadinessState> {
  return fetchSystemReadiness() as Promise<ReadinessState>;
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
