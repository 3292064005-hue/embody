import type { OperatorRole } from '@/models/safety';

export type AuditStatus = 'pending' | 'success' | 'failed' | 'blocked' | 'accepted' | 'rejected';

export interface CommandAuditRecord {
  id: string;
  action: string;
  requestId: string;
  actorRole: OperatorRole;
  createdAt: string;
  finishedAt?: string;
  status: AuditStatus;
  reason: string;
  payload?: Record<string, unknown>;
  guardSummary?: string;
  correlationId?: string;
  taskId?: string;
}
