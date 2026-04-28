import type { LogEvent } from '@/models/log';
import type { CommandAuditRecord } from '@/models/audit';
import type { CommandReceiptRecord } from '@/models/receipt';
import { getAuditLogRecords, getCommandReceiptRecords, getLogEvents } from '@/api/generated';

export async function fetchLogs(): Promise<LogEvent[]> {
  return getLogEvents();
}

export async function fetchAuditLogs(): Promise<CommandAuditRecord[]> {
  return getAuditLogRecords();
}

export async function fetchCommandReceipts(): Promise<CommandReceiptRecord[]> {
  return getCommandReceiptRecords();
}
