import type { CalibrationProfile, CalibrationProfileVersion, VisionFrame, VisionTarget } from '@/models/vision';
import type { HardwareState } from '@/models/robot';
import type { LogEvent } from '@/models/log';
import type { TaskHistoryEntry, TaskProgress, TaskTemplate } from '@/models/task';
import type { SystemState } from '@/models/system';
import { coerceSystemState } from '@/models/system';

export const mockSystemState: SystemState = coerceSystemState({
  runtimePhase: 'idle',
  controllerMode: 'idle',
  taskStage: 'done',
  rosConnected: true,
  stm32Connected: true,
  esp32Connected: true,
  cameraConnected: true,
  emergencyStop: false,
  timestamp: new Date().toISOString(),
});

export const mockHardwareState: HardwareState = {
  joints: [0, 0, 0, 0, 0, 0],
  gripperOpen: true,
  homed: true,
  limits: [false, false, false, false, false, false],
  poseName: 'home',
  busy: false,
  sourceStm32Online: true,
  sourceStm32Authoritative: true,
  sourceStm32TransportMode: 'real',
  sourceStm32Controllable: true,
  sourceStm32Simulated: false,
  sourceStm32SimulatedFallback: false,
  sourceEsp32Online: true,
  sourceEsp32StreamSemantic: 'reserved',
  sourceEsp32StreamReserved: true,
  sourceCameraFrameIngressLive: false,
  sourcePerceptionLive: false,
  rawStatus: {},
};

export const mockTargets: VisionTarget[] = [
  { id: 'target-red-1', category: 'red', pixelX: 120, pixelY: 90, worldX: 0.12, worldY: 0.08, angle: 0.1, confidence: 0.94, graspable: true },
  { id: 'target-blue-1', category: 'blue', pixelX: 240, pixelY: 160, worldX: 0.21, worldY: 0.14, angle: -0.2, confidence: 0.88, graspable: true },
];

export const mockVisionFrame: VisionFrame = {
  available: true,
  width: 640,
  height: 480,
  frameId: 'camera_optical_frame',
  source: 'frontend_fixture',
  sourceType: 'fixture',
  providerKind: 'synthetic_scene',
  providerLabel: 'synthetic_frame_stream',
  frameIngressMode: 'synthetic_frame_stream',
  frameIngressLive: true,
  cameraLive: false,
  syntheticPreview: true,
  frameTransportHealthy: true,
  authoritativeVisualSource: 'synthetic_perception',
  targetCount: mockTargets.length,
  previewDataUrl: "data:image/svg+xml;charset=UTF-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='640' height='480' viewBox='0 0 640 480'%3E%3Crect width='640' height='480' fill='%230f172a'/%3E%3Ctext x='24' y='36' fill='%23cbd5e1' font-size='18'%3EFixture Frame%3C/text%3E%3C/svg%3E",
};

export const mockTask: TaskProgress | null = null;

export const mockTemplates: TaskTemplate[] = [
  { id: 'pick-red', name: '抓取红色目标', taskType: 'pick_place', description: '单目标抓取并按红色料区放置。', defaultTargetCategory: 'red', allowedTargetCategories: ['red'], resolvedPlaceProfiles: { red: 'bin_red' }, riskLevel: 'low', requiredRuntimeTier: 'validated_sim', operatorHint: '适合单目标验证链路与基础抓取验收。' },
  { id: 'sort-color', name: '按颜色分拣', taskType: 'sort_by_color', description: '使用颜色选择器触发分拣任务。', defaultTargetCategory: 'red', allowedTargetCategories: ['red', 'blue', 'green'], resolvedPlaceProfiles: { red: 'bin_red', blue: 'bin_blue', green: 'bin_green' }, riskLevel: 'medium', requiredRuntimeTier: 'validated_sim', operatorHint: '需要颜色目标检测链路稳定。' },
];

export const mockTaskHistory: TaskHistoryEntry[] = [
  { taskId: 'history-1', taskType: 'pick_place', targetCategory: 'red', startedAt: new Date(Date.now() - 60000).toISOString(), finishedAt: new Date(Date.now() - 30000).toISOString(), success: true, retryCount: 0, durationMs: 30000, resultMessage: 'Mock 任务完成' },
  { taskId: 'history-2', taskType: 'sort_by_color', targetCategory: 'blue', startedAt: new Date(Date.now() - 120000).toISOString(), finishedAt: new Date(Date.now() - 90000).toISOString(), success: false, retryCount: 1, durationMs: 30000, resultMessage: 'Mock 任务失败' },
];

export const mockCalibration: CalibrationProfile = {
  profileName: 'default',
  roi: { x: 0, y: 0, width: 640, height: 480 },
  tableScaleMmPerPixel: 1,
  offsets: { x: 0, y: 0, z: 0 },
  updatedAt: new Date().toISOString(),
};

export const mockCalibrationVersions: CalibrationProfileVersion[] = [
  { id: 'cal-default', operator: 'maintainer', meanErrorMm: 1.2, maxErrorMm: 2.8, sampleCount: 24, active: true, ...mockCalibration },
];

export const mockLogs: LogEvent[] = [
  { id: 'log-1', timestamp: new Date().toISOString(), requestId: 'req-1', correlationId: 'corr-1', level: 'info', module: 'mock.gateway', event: 'bootstrap', message: 'Mock runtime ready' },
];
