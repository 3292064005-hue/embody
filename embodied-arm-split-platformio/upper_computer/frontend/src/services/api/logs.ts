import type { LogEvent } from '@/models/log';
import type { CommandAuditRecord } from '@/models/audit';
import { unwrapResponse, apiClient } from './client';

export async function fetchLogs(): Promise<LogEvent[]> {
  return unwrapResponse(apiClient.get('/api/logs/events'));
}

export async function fetchAuditLogs(): Promise<CommandAuditRecord[]> {
  return unwrapResponse(apiClient.get('/api/logs/audit'));
}
