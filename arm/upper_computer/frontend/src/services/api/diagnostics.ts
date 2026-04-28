import type { DiagnosticsSummary } from '@/models/diagnostics';
import { unwrapResponse, apiClient } from './client';

export async function fetchDiagnosticsSummary(): Promise<DiagnosticsSummary> {
  return unwrapResponse(apiClient.get('/api/diagnostics/summary'));
}
