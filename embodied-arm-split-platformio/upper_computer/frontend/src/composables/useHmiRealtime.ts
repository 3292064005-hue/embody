import { onMounted, onUnmounted } from 'vue';
import { HmiWebSocket } from '@/services/ws/HmiWebSocket';
import { useConnectionStore } from '@/stores/connection';
import { useSystemStore } from '@/stores/system';
import { useVisionStore } from '@/stores/vision';
import { useTaskStore } from '@/stores/task';
import { useRobotStore } from '@/stores/robot';
import { useLogStore } from '@/stores/log';
import { useDiagnosticsStore } from '@/stores/diagnostics';
import { useAuditStore } from '@/stores/audit';
import { useReadinessStore } from '@/stores/readiness';
import { requestRuntimeResync } from '@/shared/runtime/resync';
import { isFixtureMockEnabled } from '@/shared/mock/mode';
import type { SystemState } from '@/models/system';
import type { VisionTarget } from '@/models/vision';
import type { TaskProgress } from '@/models/task';
import type { HardwareState } from '@/models/robot';
import type { LogEvent } from '@/models/log';
import type { DiagnosticsSummary } from '@/models/diagnostics';
import type { ReadinessState } from '@/models/readiness';
import type { CommandAuditRecord } from '@/models/audit';

let ws: HmiWebSocket | null = null;
let consumerCount = 0;
let unsubscribers: Array<() => void> = [];
let mockHeartbeatTimer: number | null = null;

function registerSubscriptions(): void {
  const connectionStore = useConnectionStore();
  const systemStore = useSystemStore();
  const visionStore = useVisionStore();
  const taskStore = useTaskStore();
  const robotStore = useRobotStore();
  const logStore = useLogStore();
  const diagnosticsStore = useDiagnosticsStore();
  const auditStore = useAuditStore();
  const readinessStore = useReadinessStore();
  if (!ws) return;
  unsubscribers = [
    ws.subscribe('connection.open', ({ timestamp }: { timestamp: string }) => {
      connectionStore.setGatewayConnected(true);
      connectionStore.markHeartbeat(timestamp);
      connectionStore.setWsState('open');
      connectionStore.setReadonlyDegraded(false);
      connectionStore.setTransportState('resyncing');
      requestRuntimeResync('ws-open');
    }),
    ws.subscribe('connection.close', ({ timestamp }: { timestamp: string }) => {
      connectionStore.setGatewayConnected(false);
      connectionStore.markHeartbeat(timestamp);
      connectionStore.setWsState('closed');
      connectionStore.setReadonlyDegraded(true);
      connectionStore.setTransportState('degraded');
    }),
    ws.subscribe('connection.state', ({ wsState }: { wsState: Parameters<typeof connectionStore.setWsState>[0] }) => { connectionStore.setWsState(wsState); }),
    ws.subscribe('connection.heartbeat', ({ timestamp }: { timestamp: string }) => { connectionStore.markHeartbeat(timestamp); }),
    ws.subscribe('connection.pong', ({ timestamp }: { timestamp: string }) => { connectionStore.markPong(timestamp); }),
    ws.subscribe('connection.reconnect_scheduled', () => { connectionStore.incrementReconnect(); }),
    ws.subscribe('connection.parse_error', () => { connectionStore.incrementParseErrors(); connectionStore.setReadonlyDegraded(true); }),
    ws.subscribe('connection.message', ({ timestamp, latencyMs, eventName }: { timestamp: string; latencyMs: number | null; eventName: string }) => { connectionStore.markMessage(timestamp, latencyMs, eventName); }),
    ws.subscribe<SystemState>('system.state.updated', (payload) => systemStore.setState(payload)),
    ws.subscribe<VisionTarget[]>('vision.targets.updated', (payload) => visionStore.setTargets(payload)),
    ws.subscribe<TaskProgress | null>('task.progress.updated', (payload) => taskStore.setCurrentTask(payload)),
    ws.subscribe<ReadinessState>('readiness.state.updated', (payload) => readinessStore.setReadiness(payload)),
    ws.subscribe<HardwareState>('hardware.state.updated', (payload) => robotStore.setHardwareState(payload)),
    ws.subscribe<LogEvent>('log.event.created', (payload) => logStore.push(payload)),
    ws.subscribe<DiagnosticsSummary>('diagnostics.summary.updated', (payload) => diagnosticsStore.setSummary(payload)),
    ws.subscribe<CommandAuditRecord>('audit.event.created', (payload) => auditStore.mergeServerRecord(payload as unknown as Record<string, unknown>))
  ];
}

function teardownRealtime(): void {
  unsubscribers.forEach((dispose) => dispose());
  unsubscribers = [];
  ws?.disconnect();
  ws = null;
  if (mockHeartbeatTimer) { window.clearInterval(mockHeartbeatTimer); mockHeartbeatTimer = null; }
}

export function useHmiRealtime(): void {
  const connectionStore = useConnectionStore();
  onMounted(() => {
    consumerCount += 1;
    if (isFixtureMockEnabled()) {
      connectionStore.setGatewayConnected(true);
      connectionStore.setWsState('open');
      connectionStore.setReadonlyDegraded(false);
      connectionStore.setTransportState('live');
      const updateHeartbeat = () => {
        const now = new Date().toISOString();
        connectionStore.markHeartbeat(now);
        connectionStore.markPong(now);
        connectionStore.markMessage(now, 12, 'mock.heartbeat');
      };
      updateHeartbeat();
      if (!mockHeartbeatTimer) mockHeartbeatTimer = window.setInterval(updateHeartbeat, 2000);
      return;
    }
    if (!ws) {
      ws = new HmiWebSocket(import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/ws');
      registerSubscriptions();
      ws.connect();
    }
  });

  onUnmounted(() => {
    consumerCount = Math.max(consumerCount - 1, 0);
    if (consumerCount === 0) teardownRealtime();
  });
}
