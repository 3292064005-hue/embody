import type { SystemState } from '@/models/system';
import type { ReadinessState } from '@/models/readiness';
import { apiClient, postVoid, unwrapResponse } from './client';
import { fetchSystemReadiness } from '@/api/generated';

export async function fetchSystemSummary(): Promise<SystemState> {
  return unwrapResponse(apiClient.get('/api/system/summary'));
}

export async function fetchReadiness(): Promise<ReadinessState> {
  return fetchSystemReadiness();
}

export async function homeRobot(): Promise<void> {
  await postVoid('/api/system/home');
}

export async function resetFault(): Promise<void> {
  await postVoid('/api/system/reset-fault');
}

export async function recoverRuntime(): Promise<void> {
  await postVoid('/api/system/recover');
}

export async function emergencyStop(): Promise<void> {
  await postVoid('/api/system/emergency-stop');
}
