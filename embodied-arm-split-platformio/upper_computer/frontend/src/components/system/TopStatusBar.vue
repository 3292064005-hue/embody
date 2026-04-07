<template>
  <header class="top-bar panel">
    <div>
      <div class="title">{{ appStore.appTitle }}</div>
      <div class="subtle">ROS2 桌面具身智能机械臂主控 HMI · 控制面 / 观测面分离架构</div>
    </div>
    <div class="state-group">
      <div :class="['status-pill', systemClass]">
        <span class="status-dot"></span>
        <span>{{ modeLabel }}</span>
      </div>
      <div :class="['status-pill', readinessStore.runtimeHealthy ? 'status-ok' : 'status-danger']">
        <span class="status-dot"></span>
        <span>RUNTIME {{ readinessStore.runtimeHealthy ? 'READY' : 'BLOCKED' }}</span>
      </div>
      <div :class="['status-pill', readinessStore.modeReady ? 'status-ok' : 'status-warn']">
        <span class="status-dot"></span>
        <span>MODE {{ readinessStore.modeReady ? 'READY' : 'LIMITED' }}</span>
      </div>
      <div :class="['status-pill', commandPillClass]">
        <span class="status-dot"></span>
        <span>CMD {{ readinessStore.commandSummary?.readyCount || 0 }}/{{ totalCommandCount }}</span>
      </div>
      <div :class="['status-pill', connectionStore.gatewayConnected ? 'status-ok' : 'status-danger']">
        <span class="status-dot"></span>
        <span>Gateway</span>
      </div>
      <div :class="['status-pill', connectionQualityClass]">
        <span class="status-dot"></span>
        <span>{{ connectionStore.quality.toUpperCase() }}</span>
      </div>
      <div :class="['status-pill', systemStore.current?.rosConnected ? 'status-ok' : 'status-danger']">
        <span class="status-dot"></span>
        <span>ROS2</span>
      </div>
      <div :class="['status-pill', hardwareTransportClass]">
        <span class="status-dot"></span>
        <span>{{ hardwareTransportLabel }}</span>
      </div>
      <div :class="['status-pill', systemStore.current?.cameraConnected ? 'status-ok' : 'status-danger']">
        <span class="status-dot"></span>
        <span>Camera</span>
      </div>
      <el-tag>CTRL {{ controllerModeLabel }}</el-tag>
      <el-tag>TASK {{ taskStage }}</el-tag>
      <el-tag v-if="readinessStore.simulated" type="warning">SIM_RUNTIME</el-tag>
      <el-tag v-if="hardwareSimulated" type="danger">SIM_HW</el-tag>
      <el-tag v-if="connectionStore.readonlyDegraded" type="danger">READONLY</el-tag>
      <el-select :model-value="appStore.operatorRole" class="mode-switch" @change="handleModeChange">
        <el-option v-for="item in modeOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <button class="danger-btn" :disabled="systemStore.pendingCommand" @click="emitEmergencyStop">急停</button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { ElMessageBox, ElNotification } from 'element-plus';
import { OPERATOR_ROLE_OPTIONS, SYSTEM_PHASE_COLOR, SYSTEM_PHASE_LABELS } from '@/constants/system';
import { resolveControllerMode } from '@/models/system';
import { useSystemStore } from '@/stores/system';
import { useAppStore } from '@/stores/app';
import { useConnectionStore } from '@/stores/connection';
import { useSettingsStore } from '@/stores/settings';
import { useReadinessStore } from '@/stores/readiness';
import { useRobotStore } from '@/stores/robot';
import type { OperatorRole } from '@/models/safety';
import { deriveCommandPillClass, deriveHardwareTransportClass, deriveHardwareTransportLabel } from '@/components/system/statusSemantics';

const systemStore = useSystemStore();
const appStore = useAppStore();
const connectionStore = useConnectionStore();
const settingsStore = useSettingsStore();
const readinessStore = useReadinessStore();
const robotStore = useRobotStore();
const modeOptions = OPERATOR_ROLE_OPTIONS;

const runtimePhase = computed(() => systemStore.current?.runtimePhase || systemStore.current?.mode || 'boot');
const taskStage = computed(() => systemStore.current?.taskStage || systemStore.current?.currentStage || 'created');
const controllerModeLabel = computed(() => systemStore.current ? resolveControllerMode(systemStore.current as Record<string, unknown>) : 'idle');
const modeLabel = computed(() => SYSTEM_PHASE_LABELS[runtimePhase.value] || '--');
const systemClass = computed(() => SYSTEM_PHASE_COLOR[runtimePhase.value] || 'status-warn');
const connectionQualityClass = computed(() => connectionStore.quality === 'offline' ? 'status-danger' : connectionStore.quality === 'degraded' ? 'status-warn' : 'status-ok');
const totalCommandCount = computed(() => Object.keys(readinessStore.commandPolicies || {}).length || 0);
const commandPillClass = computed(() => deriveCommandPillClass(readinessStore.commandSummary, totalCommandCount.value));
const hardwareSimulated = computed(() => Boolean(robotStore.hardware?.sourceStm32Simulated));
const hardwareTransportLabel = computed(() => deriveHardwareTransportLabel(robotStore.hardware));
const hardwareTransportClass = computed(() => deriveHardwareTransportClass(robotStore.hardware));

function handleModeChange(value: OperatorRole) {
  appStore.setOperatorRole(value);
  ElNotification.success({
    title: '权限模式已切换',
    message: `当前为${modeOptions.find((item) => item.value === value)?.label || value}`
  });
}

async function emitEmergencyStop() {
  try {
    if (settingsStore.dangerConfirmRequired) {
      await ElMessageBox.confirm('急停将中断当前动作并进入安全停车态，确认继续？', '危险操作确认', {
        confirmButtonText: '确认急停',
        cancelButtonText: '取消',
        type: 'warning'
      });
    }
    await systemStore.emergencyStop();
    ElNotification.warning({ title: '急停请求已发送', message: '请以后端网关和硬件状态回执为准。' });
  } catch {
    // canceled or blocked
  }
}
</script>

<style scoped>
.top-bar { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; border-radius: 0; border-left: 0; border-right: 0; }
.title { font-size: 18px; font-weight: 800; }
.state-group { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
.mode-switch { width: 132px; }
.danger-btn { height: 40px; padding: 0 18px; border-radius: 10px; border: none; background: var(--danger); color: white; font-weight: 800; cursor: pointer; }
.danger-btn:disabled { cursor: not-allowed; opacity: 0.65; }
</style>
