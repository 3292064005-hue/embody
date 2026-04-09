export type TaskType = 'pick_place' | 'sort_by_color' | 'sort_by_qr' | 'clear_table';
export type TargetCategory = 'red' | 'blue' | 'green' | 'qr_a' | 'qr_b' | 'qr_c';
export type TaskStage = 'created' | 'perception' | 'plan' | 'execute' | 'verify' | 'done' | 'failed';

export interface TaskProgress {
  taskId: string;
  templateId?: string;
  taskType: TaskType;
  stage: TaskStage;
  percent: number;
  retryCount: number;
  startedAt: string;
  updatedAt: string;
  targetCategory?: TargetCategory;
  placeProfile?: string;
  runtimeTier?: 'preview' | 'validated_sim' | 'validated_live';
  lastMessage?: string;
}

export interface TaskTemplate {
  id: string;
  name: string;
  taskType: TaskType;
  description: string;
  defaultTargetCategory?: TargetCategory;
  allowedTargetCategories?: TargetCategory[];
  resolvedPlaceProfiles?: Record<string, string>;
  riskLevel?: 'low' | 'medium' | 'high';
  requiredRuntimeTier?: 'preview' | 'validated_sim' | 'validated_live';
  operatorHint?: string;
}

export interface TaskHistoryEntry {
  taskId: string;
  templateId?: string;
  taskType: TaskType;
  targetCategory?: TargetCategory;
  placeProfile?: string;
  runtimeTier?: 'preview' | 'validated_sim' | 'validated_live';
  startedAt: string;
  finishedAt: string;
  success: boolean;
  retryCount: number;
  durationMs: number;
  resultMessage: string;
  requestId?: string;
  correlationId?: string;
  taskRunId?: string;
}

export interface StartTaskPayload {
  taskType: TaskType;
  targetCategory?: TargetCategory;
  templateId?: string;
}
