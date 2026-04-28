import type { RuntimePhase } from '@/models/system';

export const APP_TITLE = import.meta.env.VITE_APP_TITLE || 'Embodied Arm HMI';

export const SYSTEM_PHASE_LABELS: Record<RuntimePhase, string> = {
  boot: 'BOOT',
  idle: 'IDLE',
  perception: 'PERCEPTION',
  plan: 'PLAN',
  execute: 'EXECUTE',
  verify: 'VERIFY',
  safe_stop: 'SAFE_STOP',
  fault: 'FAULT'
};

export const SYSTEM_PHASE_COLOR: Record<RuntimePhase, string> = {
  boot: 'status-warn',
  idle: 'status-ok',
  perception: 'status-ok',
  plan: 'status-ok',
  execute: 'status-warn',
  verify: 'status-ok',
  safe_stop: 'status-warn',
  fault: 'status-danger'
};

export const SYSTEM_PHASE_TEXT: Record<RuntimePhase, string> = {
  boot: '系统自检与上电初始化',
  idle: '待机，可接收任务',
  perception: '视觉采集与目标识别',
  plan: '规划预抓取与放置动作',
  execute: '机械臂执行阶段',
  verify: '结果验证与重试判定',
  safe_stop: '安全停车，等待人工确认',
  fault: '故障锁定，禁止危险操作'
};

export const LOG_LEVEL_OPTIONS = [
  { label: '全部', value: 'all' },
  { label: 'INFO', value: 'info' },
  { label: 'WARN', value: 'warn' },
  { label: 'ERROR', value: 'error' },
  { label: 'FAULT', value: 'fault' }
] as const;

export const OPERATOR_ROLE_OPTIONS = [
  { label: '观察者', value: 'viewer' },
  { label: '操作员', value: 'operator' },
  { label: '维护员', value: 'maintainer' }
] as const;

export const CONTROLLER_MODE_OPTIONS = [
  { label: '空闲模式', value: 'idle' },
  { label: '手动模式', value: 'manual' },
  { label: '任务模式', value: 'task' },
  { label: '维护模式', value: 'maintenance' }
] as const;
