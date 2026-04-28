export interface ApiResponse<T> {
  code: number;
  message: string;
  requestId: string;
  correlationId?: string | null;
  timestamp: string;
  data: T;
}

export interface ApiErrorPayload {
  code: number;
  error?: string;
  failureClass?: string | null;
  message: string;
  requestId?: string;
  timestamp?: string;
  detail?: string;
  operatorActionable?: boolean | null;
}

export interface WsEvent<T> {
  event: string;
  timestamp: string;
  source?: 'gateway' | 'embodied-arm-hmi' | 'mock-runtime' | string;
  taskId?: string;
  level?: 'info' | 'warn' | 'error' | 'fault';
  requestId?: string;
  correlationId?: string;
  seq?: number;
  schemaVersion?: string;
  snapshotVersion?: number;
  bootstrapComplete?: boolean;
  deliveryMode?: 'snapshot' | 'delta' | 'event';
  topic?: string;
  topicRevision?: number;
  data: T;
}

export class ApiClientError extends Error {
  readonly status?: number;
  readonly code?: number;
  readonly requestId?: string;
  readonly detail?: string;
  readonly error?: string;
  readonly failureClass?: string | null;
  readonly operatorActionable?: boolean | null;

  constructor(message: string, options?: { status?: number; code?: number; requestId?: string; detail?: string; error?: string; failureClass?: string | null; operatorActionable?: boolean | null }) {
    super(message);
    this.name = 'ApiClientError';
    this.status = options?.status;
    this.code = options?.code;
    this.requestId = options?.requestId;
    this.detail = options?.detail;
    this.error = options?.error;
    this.failureClass = options?.failureClass;
    this.operatorActionable = options?.operatorActionable;
  }
}
