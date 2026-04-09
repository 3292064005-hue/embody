import { computed } from 'vue';
import { defineStore } from 'pinia';
import type { SafetySnapshot } from '@/models/safety';
import { useAppStore } from './app';
import { useConnectionStore } from './connection';
import { useRobotStore } from './robot';
import { useSystemStore } from './system';
import { useReadinessStore } from './readiness';
import { createSafetySnapshot, evaluateGripper, evaluateHome, evaluateJog, evaluateRecover, evaluateResetFault, evaluateServoCartesian, evaluateStartTask, evaluateStopTask, summarizeSafetySnapshot } from '@/domain/safety/guards';

export const useSafetyStore = defineStore('safety', () => {
  const appStore = useAppStore();
  const connectionStore = useConnectionStore();
  const robotStore = useRobotStore();
  const systemStore = useSystemStore();
  const readinessStore = useReadinessStore();

  const snapshot = computed<SafetySnapshot>(() => createSafetySnapshot({
    operatorRole: appStore.operatorRole,
    gatewayConnected: connectionStore.gatewayConnected,
    realtimeStale: connectionStore.isRealtimeStale,
    emergencyStop: Boolean(systemStore.current?.emergencyStop),
    faultMode: systemStore.isFault,
    systemBusy: systemStore.isBusy,
    hardwareBusy: Boolean(robotStore.hardware?.busy),
    homed: Boolean(robotStore.hardware?.homed),
    readonlyDegraded: connectionStore.readonlyDegraded,
    commandPolicies: readinessStore.commandPolicies
  }));

  const canStartTask = computed(() => evaluateStartTask(snapshot.value));
  const canStopTask = computed(() => evaluateStopTask(snapshot.value));
  const canJog = computed(() => evaluateJog(snapshot.value));
  const canServoCartesian = computed(() => evaluateServoCartesian(snapshot.value));
  const canControlGripper = computed(() => evaluateGripper(snapshot.value));
  const canResetFault = computed(() => evaluateResetFault(snapshot.value));
  const canRecover = computed(() => evaluateRecover(snapshot.value));
  const canHomeRobot = computed(() => evaluateHome(snapshot.value));
  const guardSummary = computed(() => summarizeSafetySnapshot(snapshot.value));

  return { snapshot, guardSummary, canStartTask, canStopTask, canJog, canServoCartesian, canControlGripper, canResetFault, canRecover, canHomeRobot };
});
