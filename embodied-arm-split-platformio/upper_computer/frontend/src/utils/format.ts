export function formatPercent(value: number): string {
  return `${Math.round(value)}%`;
}

export function formatDateTime(value?: string): string {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`;
}

export function formatJoint(rad: number): string {
  return `${((rad * 180) / Math.PI).toFixed(1)}°`;
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

export function formatLatency(value: number | null | undefined): string {
  if (value == null) return '--';
  return `${Math.round(value)} ms`;
}

export function formatBool(value: boolean): string {
  return value ? '是' : '否';
}
