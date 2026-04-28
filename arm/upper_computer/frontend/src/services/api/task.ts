import type { StartTaskPayload, TaskHistoryEntry, TaskProgress, TaskTemplate } from '@/models/task';
import { startTask as startTaskRequest, stopTaskCommand, type CommandTransportResult as GeneratedCommandTransportResult, type StartTaskDecision } from '@/api/generated';
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

export interface TaskCommandResult extends GeneratedCommandTransportResult {}

export async function stopTask(): Promise<TaskCommandResult> {
  return stopTaskCommand();
}
