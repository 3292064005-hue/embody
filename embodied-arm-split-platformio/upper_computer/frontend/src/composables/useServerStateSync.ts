import { onMounted, onUnmounted, watch } from 'vue';
import { fetchSystemSummary, fetchReadiness } from '@/services/api/system';
import { fetchTargets, fetchCalibrationProfile, fetchCalibrationVersions } from '@/services/api/vision';
import { fetchCurrentTask, fetchTaskHistory, fetchTaskTemplates } from '@/services/api/task';
import { fetchHardwareState } from '@/services/api/hardware';
import { fetchAuditLogs, fetchLogs } from '@/services/api/logs';
import { fetchDiagnosticsSummary } from '@/services/api/diagnostics';
import { useSystemStore } from '@/stores/system';
import { useVisionStore } from '@/stores/vision';
import { useTaskStore } from '@/stores/task';
import { useRobotStore } from '@/stores/robot';
import { useLogStore } from '@/stores/log';
import { useSettingsStore } from '@/stores/settings';
import { useConnectionStore } from '@/stores/connection';
import { useReadinessStore } from '@/stores/readiness';
import { useDiagnosticsStore } from '@/stores/diagnostics';
import { useAuditStore } from '@/stores/audit';
import { subscribeInvalidation, type InvalidationTopic } from '@/shared/runtime/invalidation';
import { subscribeRuntimeResync } from '@/shared/runtime/resync';

type ResourceDefinition = {
  topic: InvalidationTopic;
  intervalMs?: number;
  fetcher: () => Promise<unknown>;
  apply: (payload: unknown) => void;
  mode: 'boot' | 'poll';
};

export function useServerStateSync(): void {
  const systemStore = useSystemStore();
  const visionStore = useVisionStore();
  const taskStore = useTaskStore();
  const robotStore = useRobotStore();
  const logStore = useLogStore();
  const settingsStore = useSettingsStore();
  const connectionStore = useConnectionStore();
  const readinessStore = useReadinessStore();
  const diagnosticsStore = useDiagnosticsStore();
  const auditStore = useAuditStore();

  const inflight = new Map<InvalidationTopic, Promise<void>>();
  const timers = new Map<InvalidationTopic, number>();
  let unsubscribeInvalidation: (() => void) | null = null;
  let unsubscribeResync: (() => void) | null = null;

  const resources: ResourceDefinition[] = [
    { topic: 'system', fetcher: fetchSystemSummary, apply: (payload) => systemStore.setState(payload as Awaited<ReturnType<typeof fetchSystemSummary>>), mode: 'boot' },
    { topic: 'readiness', fetcher: fetchReadiness, apply: (payload) => readinessStore.setReadiness(payload as Awaited<ReturnType<typeof fetchReadiness>>), mode: 'boot' },
    { topic: 'diagnostics', fetcher: fetchDiagnosticsSummary, apply: (payload) => diagnosticsStore.setSummary(payload as Awaited<ReturnType<typeof fetchDiagnosticsSummary>>), mode: 'boot' },
    { topic: 'task.current', fetcher: fetchCurrentTask, apply: (payload) => taskStore.setCurrentTask(payload as Awaited<ReturnType<typeof fetchCurrentTask>>), mode: 'boot' },
    { topic: 'vision.targets', fetcher: fetchTargets, apply: (payload) => visionStore.setTargets(payload as Awaited<ReturnType<typeof fetchTargets>>), mode: 'boot' },
    { topic: 'hardware', fetcher: fetchHardwareState, apply: (payload) => robotStore.setHardwareState(payload as Awaited<ReturnType<typeof fetchHardwareState>>), mode: 'boot' },
    { topic: 'task.templates', intervalMs: 30000, fetcher: fetchTaskTemplates, apply: (payload) => taskStore.setTemplates(payload as Awaited<ReturnType<typeof fetchTaskTemplates>>), mode: 'poll' },
    { topic: 'task.history', intervalMs: 5000, fetcher: fetchTaskHistory, apply: (payload) => taskStore.setHistory(payload as Awaited<ReturnType<typeof fetchTaskHistory>>), mode: 'poll' },
    { topic: 'vision.calibration', intervalMs: 20000, fetcher: fetchCalibrationProfile, apply: (payload) => visionStore.setCalibration(payload as Awaited<ReturnType<typeof fetchCalibrationProfile>>), mode: 'poll' },
    { topic: 'vision.versions', intervalMs: 20000, fetcher: fetchCalibrationVersions, apply: (payload) => visionStore.setVersions(payload as Awaited<ReturnType<typeof fetchCalibrationVersions>>), mode: 'poll' },
    { topic: 'logs', intervalMs: 4000, fetcher: fetchLogs, apply: (payload) => logStore.setRecords(payload as Awaited<ReturnType<typeof fetchLogs>>), mode: 'poll' },
    { topic: 'audit', intervalMs: 5000, fetcher: fetchAuditLogs, apply: (payload) => auditStore.setRecords(payload as Awaited<ReturnType<typeof fetchAuditLogs>>), mode: 'poll' }
  ];

  const bootTopics = resources.filter((item) => item.mode === 'boot').map((item) => item.topic);
  const polledTopics = resources.filter((item) => item.mode === 'poll').map((item) => item.topic);

  function schedule(definition: ResourceDefinition) {
    const existing = timers.get(definition.topic);
    if (existing) window.clearInterval(existing);
    if (!settingsStore.autoRefresh || definition.mode !== 'poll' || !definition.intervalMs) return;
    const timer = window.setInterval(() => { void refresh(definition.topic); }, definition.intervalMs);
    timers.set(definition.topic, timer);
  }

  async function refresh(topic: InvalidationTopic) {
    const definition = resources.find((item) => item.topic === topic);
    if (!definition) return;
    if (inflight.has(topic)) return inflight.get(topic);
    const task = (async () => {
      try {
        const payload = await definition.fetcher();
        definition.apply(payload);
        connectionStore.markServerSync(new Date().toISOString(), topic);
      } catch (error) {
        connectionStore.incrementSyncError();
        console.error(`[server-sync] ${topic} failed`, error);
      } finally {
        inflight.delete(topic);
      }
    })();
    inflight.set(topic, task);
    return task;
  }

  async function bootstrap(reason: string) {
    connectionStore.setTransportState(reason === 'initial' ? 'bootstrapping' : 'resyncing');
    await Promise.allSettled(bootTopics.map((topic) => refresh(topic)));
    if (connectionStore.gatewayConnected) connectionStore.setTransportState('live');
  }

  function start() {
    void bootstrap('initial');
    polledTopics.forEach((topic) => { void refresh(topic); });
    resources.forEach((definition) => { schedule(definition); });
    unsubscribeInvalidation = subscribeInvalidation((topic) => {
      const definition = resources.find((item) => item.topic === topic);
      if (!definition || definition.mode !== 'poll') return;
      void refresh(topic);
    });
    unsubscribeResync = subscribeRuntimeResync((reason) => { void bootstrap(reason); });
  }

  function stop() {
    timers.forEach((value) => window.clearInterval(value));
    timers.clear();
    unsubscribeInvalidation?.();
    unsubscribeInvalidation = null;
    unsubscribeResync?.();
    unsubscribeResync = null;
  }

  onMounted(start);
  onUnmounted(stop);
  watch(() => settingsStore.autoRefresh, () => { resources.forEach((definition) => schedule(definition)); });
}
