import type { SystemState } from '@/models/system';
import type { ReadinessState } from '@/models/readiness';
import { unwrapResponse, apiClient, postVoid } from './client';

export async function fetchSystemSummary(): Promise<SystemState> {
  return unwrapResponse(apiClient.get('/api/system/summary'));
}

export async function fetchReadiness(): Promise<ReadinessState> {
  return unwrapResponse(apiClient.get('/api/system/readiness'));
}

export async function homeRobot(): Promise<void> {
  await postVoid('/api/system/home');
}

export async function resetFault(): Promise<void> {
  await postVoid('/api/system/reset-fault');
}

export async function emergencyStop(): Promise<void> {
  await postVoid('/api/system/emergency-stop');
}
