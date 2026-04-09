import type { GuardDecision, SafetySnapshot } from '@/models/safety';
import type { PublicCommandName } from '@/generated/runtimeContract';

function allow(reason = '允许执行'): GuardDecision {
  return { allowed: true, reason };
}

function block(reason: string): GuardDecision {
  return { allowed: false, reason };
}

function fromBackendPolicy(snapshot: SafetySnapshot, commandName: PublicCommandName): GuardDecision | null {
  const policy = snapshot.commandPolicies?.[commandName];
  if (!policy) return null;
  return policy.allowed ? allow(policy.reason || '允许执行') : block(policy.reason || '后端策略阻止该命令');
}

export function createSafetySnapshot(snapshot: SafetySnapshot): SafetySnapshot {
  return snapshot;
}

function requireControlRole(snapshot: SafetySnapshot): GuardDecision | null {
  if (snapshot.operatorRole === 'viewer') return block('观察者权限仅允许查看，不允许发出控制命令');
  return null;
}

export function evaluateCommonHardStop(snapshot: SafetySnapshot): GuardDecision | null {
  if (!snapshot.gatewayConnected) return block('网关未连接，禁止发出控制命令');
  if (snapshot.readonlyDegraded) return block('系统处于只读降级态，请先恢复实时链路与同步状态');
  if (snapshot.realtimeStale) return block('实时链路过期，请先恢复连接后再操作');
  if (snapshot.emergencyStop) return block('系统已处于急停态，请先人工解除');
  return null;
}

export function evaluateStartTask(snapshot: SafetySnapshot): GuardDecision {
  const roleDecision = requireControlRole(snapshot);
  if (roleDecision) return roleDecision;
  const hardStop = evaluateCommonHardStop(snapshot);
  if (hardStop) return hardStop;
  const backendPolicy = fromBackendPolicy(snapshot, 'startTask');
  if (backendPolicy) return backendPolicy;
  if (snapshot.systemBusy || snapshot.hardwareBusy) return block('系统执行中，禁止重复启动任务');
  return allow();
}

export function evaluateStopTask(snapshot: SafetySnapshot): GuardDecision {
  const roleDecision = requireControlRole(snapshot);
  if (roleDecision) return roleDecision;
  const backendPolicy = fromBackendPolicy(snapshot, 'stopTask');
  if (backendPolicy) return backendPolicy;
  if (!snapshot.gatewayConnected && !snapshot.systemBusy && !snapshot.hardwareBusy) {
    return block('当前无有效实时连接，且系统未执行任务');
  }
  return allow('允许发出停止任务命令');
}

export function evaluateJog(snapshot: SafetySnapshot): GuardDecision {
  const hardStop = evaluateCommonHardStop(snapshot);
  if (hardStop) return hardStop;
  if (snapshot.operatorRole !== 'maintainer') return block('仅维护员权限允许点动与伺服控制');
  const backendPolicy = fromBackendPolicy(snapshot, 'jog');
  if (backendPolicy) return backendPolicy;
  if (snapshot.systemBusy || snapshot.hardwareBusy) return block('机械臂忙碌中，禁止点动');
  return allow();
}

export function evaluateServoCartesian(snapshot: SafetySnapshot): GuardDecision {
  const hardStop = evaluateCommonHardStop(snapshot);
  if (hardStop) return hardStop;
  if (snapshot.operatorRole !== 'maintainer') return block('仅维护员权限允许笛卡尔微调');
  const backendPolicy = fromBackendPolicy(snapshot, 'servoCartesian');
  if (backendPolicy) return backendPolicy;
  if (snapshot.systemBusy || snapshot.hardwareBusy) return block('机械臂忙碌中，禁止笛卡尔微调');
  return allow();
}

export function evaluateGripper(snapshot: SafetySnapshot): GuardDecision {
  const roleDecision = requireControlRole(snapshot);
  if (roleDecision) return roleDecision;
  const hardStop = evaluateCommonHardStop(snapshot);
  if (hardStop) return hardStop;
  const backendPolicy = fromBackendPolicy(snapshot, 'gripper');
  if (backendPolicy) return backendPolicy;
  return allow();
}

export function evaluateResetFault(snapshot: SafetySnapshot): GuardDecision {
  const roleDecision = requireControlRole(snapshot);
  if (roleDecision) return roleDecision;
  if (!snapshot.gatewayConnected) return block('网关离线，无法执行故障复位');
  const backendPolicy = fromBackendPolicy(snapshot, 'resetFault');
  if (backendPolicy) return backendPolicy;
  if (!snapshot.faultMode) return block('当前不在故障态，无需复位');
  return allow('允许执行故障复位');
}

export function evaluateRecover(snapshot: SafetySnapshot): GuardDecision {
  const roleDecision = requireControlRole(snapshot);
  if (roleDecision) return roleDecision;
  if (!snapshot.gatewayConnected) return block('网关离线，无法执行运行时恢复');
  const backendPolicy = fromBackendPolicy(snapshot, 'recover');
  if (backendPolicy) return backendPolicy;
  return allow('允许执行运行时恢复');
}

export function evaluateHome(snapshot: SafetySnapshot): GuardDecision {
  const roleDecision = requireControlRole(snapshot);
  if (roleDecision) return roleDecision;
  const hardStop = evaluateCommonHardStop(snapshot);
  if (hardStop) return hardStop;
  const backendPolicy = fromBackendPolicy(snapshot, 'home');
  if (backendPolicy) return backendPolicy;
  if (snapshot.systemBusy || snapshot.hardwareBusy) return block('执行中禁止回零');
  return allow();
}

export function summarizeSafetySnapshot(snapshot: SafetySnapshot): string {
  const parts = [
    `role=${snapshot.operatorRole}`,
    snapshot.gatewayConnected ? 'gateway=online' : 'gateway=offline',
    snapshot.realtimeStale ? 'realtime=stale' : 'realtime=fresh',
    snapshot.readonlyDegraded ? 'ui=readonly' : 'ui=active',
    snapshot.homed ? 'homed=yes' : 'homed=no',
    snapshot.faultMode ? 'fault=yes' : 'fault=no',
    snapshot.systemBusy || snapshot.hardwareBusy ? 'busy=yes' : 'busy=no'
  ];
  return parts.join('; ');
}
