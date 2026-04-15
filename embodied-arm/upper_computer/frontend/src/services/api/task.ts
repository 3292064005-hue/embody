import type { StartTaskPayload, TaskHistoryEntry, TaskProgress, TaskTemplate } from '@/models/task';
import { startTask as startTaskRequest, type StartTaskDecision } from '@/api/generated';
import type { CommandTransportResult } from './commandResult';
import { unwrapResponse, apiClient } from './client';

export type StartTaskResponse = StartTaskDecision;

export async function fetchCurrentTask(): Promise<TaskProgress | null> {
  return unwrapResponse(apiClient.get('/api/task/current'));
}

export async function fetchTaskTemplates(): Promise<TaskTemplate[]> {
  return unwrapResponse(apiClient.get('/api/task/templates'));
}

export async function fetchTaskHistory(): Promise<TaskHistoryEntry[]> {
  return unwrapResponse(apiClient.get('/api/task/history'));
}

export async function startTask(payload: StartTaskPayload): Promise<StartTaskResponse> {
  return startTaskRequest(payload);
}

export interface TaskCommandResult extends CommandTransportResult {}

export async function stopTask(): Promise<TaskCommandResult> {
  return unwrapResponse(apiClient.post('/api/task/stop'));
}
