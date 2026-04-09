<template>
  <section class="dashboard-page">
    <div class="grid-4 summary-grid">
      <MetricCard label="运行相位" :value="runtimePhase" hint="与 ROS2 总状态同步" :tone="systemTone" />
      <MetricCard label="目标识别数" :value="visionStore.targets.length" hint="当前 ROI 内目标数量" tone="success" />
      <MetricCard label="任务成功率" :value="`${taskStore.successRate}%`" hint="根据任务历史统计" :tone="taskStore.successRate >= 80 ? 'success' : 'warning'" />
      <MetricCard label="链路 / 控制态" :value="connectionBadge" hint="结合链路质量和只读降级状态" :tone="connectionTone" />
    </div>

    <div class="main-grid">
      <div class="left-column">
        <VideoPanel :targets="visionStore.targets" :frame="visionStore.frame" />
        <EventTimeline :records="logStore.records" :limit="10" />
      </div>
      <div class="right-column">
        <TaskControlPanel />
        <RobotStatusPanel />
        <TargetTable :targets="visionStore.targets" />
        <section class="panel state-explain">
          <div class="panel-title">状态解释</div>
          <div class="subtle body-text">{{ phaseText }}</div>
          <div class="subtle body-text">控制模式：{{ controllerMode }} / 任务阶段：{{ taskStage }}</div>
          <div class="subtle body-text">当前控制状态：{{ connectionStore.readonlyDegraded ? '只读降级，建议先恢复同步后再发命令。' : '正常可控，仍需满足具体动作门禁。' }}</div>
          <div class="subtle body-text">Runtime：{{ runtimeText }}</div>
          <div class="subtle body-text">Mode：{{ modeText }}</div>
          <div class="subtle body-text">Commands：{{ commandText }}</div>
          <div class="subtle body-text">Diagnostics：{{ diagnosticsText }}</div>
        </section>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import MetricCard from '@/components/common/MetricCard.vue';
import VideoPanel from '@/components/vision/VideoPanel.vue';
import TaskControlPanel from '@/components/task/TaskControlPanel.vue';
import RobotStatusPanel from '@/components/robot/RobotStatusPanel.vue';
import TargetTable from '@/components/vision/TargetTable.vue';
import EventTimeline from '@/components/log/EventTimeline.vue';
import { useSystemStore } from '@/stores/system';
import { useVisionStore } from '@/stores/vision';
import { useTaskStore } from '@/stores/task';
import { useConnectionStore } from '@/stores/connection';
import { useLogStore } from '@/stores/log';
import { useReadinessStore } from '@/stores/readiness';
import { useDiagnosticsStore } from '@/stores/diagnostics';
import { SYSTEM_PHASE_TEXT } from '@/constants/system';
import { resolveControllerMode } from '@/models/system';
import { deriveCommandText, deriveDiagnosticsText, deriveModeText, deriveRuntimeText } from '@/pages/dashboardSemantics';

const systemStore = useSystemStore();
const visionStore = useVisionStore();
const taskStore = useTaskStore();
const connectionStore = useConnectionStore();
const logStore = useLogStore();
const readinessStore = useReadinessStore();
const diagnosticsStore = useDiagnosticsStore();

const runtimePhase = computed(() => systemStore.current?.runtimePhase || systemStore.current?.mode || 'boot');
const controllerMode = computed(() => systemStore.current ? resolveControllerMode(systemStore.current as Record<string, unknown>) : 'idle');
const taskStage = computed(() => systemStore.current?.taskStage || systemStore.current?.currentStage || 'created');

const systemTone = computed(() => {
  const phase = runtimePhase.value;
  if (phase === 'fault') return 'danger';
  if (phase === 'execute' || phase === 'safe_stop' || phase === 'plan') return 'warning';
  return 'success';
});

const connectionTone = computed(() => {
  if (connectionStore.readonlyDegraded) return 'danger';
  if (connectionStore.quality === 'degraded') return 'warning';
  return 'success';
});

const connectionBadge = computed(() => {
  if (connectionStore.readonlyDegraded) return 'READONLY';
  return connectionStore.quality.toUpperCase();
});

const phaseText = computed(() => SYSTEM_PHASE_TEXT[runtimePhase.value]);
const readinessText = computed(() => {
  const first = readinessStore.failingChecks[0];
  return first ? `${first.name}: ${first.detail}` : '等待网关回传 readiness。';
});
const runtimeText = computed(() => deriveRuntimeText(readinessStore.runtimeHealthy, readinessStore.simulated, readinessStore.runtimeMissingChecks));
const modeText = computed(() => deriveModeText(readinessStore.modeReady, readinessStore.failingChecks));
const commandText = computed(() => deriveCommandText(readinessStore.commandSummary, readinessStore.commandPolicies));
const diagnosticsText = computed(() => deriveDiagnosticsText(diagnosticsStore));
</script>

<style scoped>
.dashboard-page { display: flex; flex-direction: column; gap: 16px; }
.main-grid { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(360px, 0.8fr); gap: 16px; }
.left-column, .right-column { display: flex; flex-direction: column; gap: 16px; }
.state-explain { padding: 16px; }
.body-text { margin-top: 10px; line-height: 1.7; }
</style>
