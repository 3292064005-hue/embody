import type { CommandSummary, ReadinessCommandPolicy, ReadinessMissingDetail } from '@/models/readiness';

export function deriveRuntimeText(runtimeHealthy: boolean | undefined, simulated: boolean | undefined, runtimeMissingChecks: string[] | undefined): string {
  if (runtimeHealthy) {
    return simulated ? '运行时核心健康，但当前是显式模拟 runtime。' : '运行时核心链路健康。';
  }
  const missing = runtimeMissingChecks?.[0];
  return missing ? `运行时核心未闭环，首个阻塞项：${missing}。` : '运行时核心尚未健康。';
}

export function deriveModeText(modeReady: boolean | undefined, failingChecks: ReadinessMissingDetail[] | undefined): string {
  if (modeReady) return '当前控制模式已满足模式级门禁。';
  const first = failingChecks?.[0];
  return `当前模式未就绪：${first ? `${first.name}: ${first.detail}` : '等待网关回传 readiness。'}`;
}

export function deriveCommandText(commandSummary: CommandSummary | undefined, commandPolicies: Record<string, ReadinessCommandPolicy> | undefined): string {
  if (!commandSummary) return '等待命令门禁策略。';
  if (commandSummary.blockedCount === 0) return `当前公开命令全部可执行，共 ${commandSummary.readyCount} 项。`;
  const firstBlocked = Object.entries(commandPolicies || {}).find(([, policy]) => !policy.allowed);
  if (!firstBlocked) return `当前允许 ${commandSummary.readyCount} 项命令，阻塞 ${commandSummary.blockedCount} 项。`;
  return `允许 ${commandSummary.readyCount} 项命令，阻塞 ${commandSummary.blockedCount} 项；首个阻塞：${firstBlocked[0]} / ${firstBlocked[1].reason}`;
}

export function deriveDiagnosticsText(payload: {
  updatedAt?: string;
  ready?: boolean;
  degraded?: boolean;
  taskSuccessRate?: number | null;
  faultCount?: number | null;
}): string {
  if (!payload.updatedAt) return '等待诊断摘要。';
  const rate = payload.taskSuccessRate == null ? '--' : `${payload.taskSuccessRate}%`;
  return `ready=${payload.ready ? 'yes' : 'no'} / degraded=${payload.degraded ? 'yes' : 'no'} / successRate=${rate} / faultCount=${payload.faultCount ?? 0}`;
}
