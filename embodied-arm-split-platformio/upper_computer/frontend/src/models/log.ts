export type LogLevel = 'info' | 'warn' | 'error' | 'fault';

export interface LogEvent {
  id: string;
  timestamp: string;
  level: LogLevel;
  module: string;
  taskId?: string;
  requestId?: string;
  correlationId?: string;
  taskRunId?: string;
  event: string;
  message: string;
  payload?: Record<string, unknown>;
}
