import type { LogEvent } from '@/models/log';
import type { CommandAuditRecord } from '@/models/audit';
import type { CommandReceiptRecord } from '@/models/receipt';
import { unwrapResponse, apiClient } from './client';

export async function fetchLogs(): Promise<LogEvent[]> {
  return unwrapResponse(apiClient.get('/api/logs/events'));
}

export async function fetchAuditLogs(): Promise<CommandAuditRecord[]> {
  return unwrapResponse(apiClient.get('/api/logs/audit'));
}

export async function fetchCommandReceipts(): Promise<CommandReceiptRecord[]> {
  return unwrapResponse(apiClient.get('/api/logs/receipts'));
}
