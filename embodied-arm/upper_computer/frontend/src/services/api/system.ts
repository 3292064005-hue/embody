import type { SystemState } from '@/models/system';
import type { ReadinessState } from '@/models/readiness';
import type { CommandTransportResult } from './commandResult';
import { apiClient, unwrapResponse } from './client';
import { fetchSystemReadiness } from '@/api/generated';

export async function fetchSystemSummary(): Promise<SystemState> {
  return unwrapResponse(apiClient.get('/api/system/summary'));
}

export async function fetchReadiness(): Promise<ReadinessState> {
  return fetchSystemReadiness();
}

export interface SystemCommandResult extends CommandTransportResult {}

export async function homeRobot(): Promise<SystemCommandResult> {
  return unwrapResponse(apiClient.post('/api/system/home'));
}

export async function resetFault(): Promise<SystemCommandResult> {
  return unwrapResponse(apiClient.post('/api/system/reset-fault'));
}

export async function recoverRuntime(): Promise<SystemCommandResult> {
  return unwrapResponse(apiClient.post('/api/system/recover'));
}

export async function emergencyStop(): Promise<SystemCommandResult> {
  return unwrapResponse(apiClient.post('/api/system/emergency-stop'));
}
