import type { CommandLifecycleStatus } from '@/services/api/commandResult';

export type CommandLifecycleTerminalStatus = 'success' | 'failed' | 'blocked' | 'rejected' | 'observed';
export type CommandLifecyclePhase = 'accepted' | CommandLifecycleTerminalStatus;

export interface CommandLifecycleExpectation {
  taskId?: string;
  taskRunId?: string;
  controllerMode?: string;
  gripperOpen?: boolean;
  runtimePhase?: string;
  emergencyStop?: boolean;
}

export interface CommandLifecycleRecord {
  id: string;
  action: string;
  requestId: string;
  operationId?: string;
  receiptId?: string;
  acceptedAt: string;
  updatedAt: string;
  finalizedAt?: string;
  status: CommandLifecyclePhase;
  authoritativeStatus?: CommandLifecycleStatus | string;
  completionPending: boolean;
  localPreviewOnly: boolean;
  message: string;
  payload?: Record<string, unknown>;
  expectation?: CommandLifecycleExpectation;
}
