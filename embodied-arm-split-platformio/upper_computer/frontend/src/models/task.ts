export type TaskType = 'pick_place' | 'sort_by_color' | 'sort_by_qr' | 'clear_table';
export type TaskStage = 'created' | 'perception' | 'plan' | 'execute' | 'verify' | 'done' | 'failed';

export interface TaskProgress {
  taskId: string;
  taskType: TaskType;
  stage: TaskStage;
  percent: number;
  retryCount: number;
  startedAt: string;
  updatedAt: string;
  targetCategory?: string;
  lastMessage?: string;
}

export interface TaskTemplate {
  id: string;
  name: string;
  taskType: TaskType;
  description: string;
  defaultTargetCategory?: string;
  riskLevel?: 'low' | 'medium' | 'high';
}

export interface TaskHistoryEntry {
  taskId: string;
  taskType: TaskType;
  targetCategory?: string;
  startedAt: string;
  finishedAt: string;
  success: boolean;
  retryCount: number;
  durationMs: number;
  resultMessage: string;
}

export interface StartTaskPayload {
  taskType: TaskType;
  targetCategory?: string;
  templateId?: string;
}
