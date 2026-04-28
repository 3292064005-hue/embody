export type CommandReceiptStatus = 'accepted' | 'success' | 'failed' | 'blocked' | 'observed' | 'rejected' | string;

export interface CommandReceiptRecord {
  id: string;
  timestamp: string;
  action: string;
  status: CommandReceiptStatus;
  role: string;
  requestId: string;
  correlationId?: string;
  commandPlane: string;
  receiptClass: string;
  executionBound: boolean;
  errorCode?: string | null;
  operatorActionable?: boolean | null;
  message: string;
  payload?: Record<string, unknown>;
}
