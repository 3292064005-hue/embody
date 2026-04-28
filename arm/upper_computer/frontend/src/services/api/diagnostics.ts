import type { DiagnosticsSummary } from '@/models/diagnostics';
import { getDiagnosticsSummary } from '@/api/generated';

export async function fetchDiagnosticsSummary(): Promise<DiagnosticsSummary> {
  return getDiagnosticsSummary();
}
