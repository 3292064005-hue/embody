import type { StartTaskPayload, TaskHistoryEntry, TaskProgress, TaskTemplate } from '@/models/task';
import {
  getCurrentTask,
  getTaskHistory,
  getTaskTemplates,
  startTask as startTaskRequest,
  stopTaskCommand,
  type CommandTransportResult as GeneratedCommandTransportResult,
  type StartTaskDecision,
} from '@/api/generated';

export type StartTaskResponse = StartTaskDecision;

export async function fetchCurrentTask(): Promise<TaskProgress | null> {
  return getCurrentTask();
}

export async function fetchTaskTemplates(): Promise<TaskTemplate[]> {
  return getTaskTemplates();
}

export async function fetchTaskHistory(): Promise<TaskHistoryEntry[]> {
  return getTaskHistory();
}

export async function startTask(payload: StartTaskPayload): Promise<StartTaskResponse> {
  return startTaskRequest(payload);
}

export interface TaskCommandResult extends GeneratedCommandTransportResult {}

export async function stopTask(): Promise<TaskCommandResult> {
  return stopTaskCommand();
}
