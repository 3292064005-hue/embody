import type { StartTaskPayload, TaskHistoryEntry, TaskProgress, TaskTemplate } from '@/models/task';
import { unwrapResponse, apiClient, postVoid } from './client';

export async function fetchCurrentTask(): Promise<TaskProgress | null> {
  return unwrapResponse(apiClient.get('/api/task/current'));
}

export async function fetchTaskTemplates(): Promise<TaskTemplate[]> {
  return unwrapResponse(apiClient.get('/api/task/templates'));
}

export async function fetchTaskHistory(): Promise<TaskHistoryEntry[]> {
  return unwrapResponse(apiClient.get('/api/task/history'));
}

export async function startTask(payload: StartTaskPayload): Promise<void> {
  await postVoid('/api/task/start', payload);
}

export async function stopTask(): Promise<void> {
  await postVoid('/api/task/stop');
}
