<template>
  <section class="maintenance-page">
    <el-alert v-if="previewNotice" type="warning" :closable="false" show-icon :title="previewNotice" />
    <div class="grid-2">
      <div class="panel action-panel">
        <div class="panel-title">维护操作</div>
        <div class="subtle">维护页仅推荐维护员使用；所有动作都进入审计链并受统一门禁控制。</div>

        <div class="mode-card panel">
          <div class="panel-title">控制器模式</div>
          <div class="joint-form">
            <el-select :model-value="controllerMode" :disabled="appStore.operatorRole !== 'maintainer' || robotStore.pendingCommand" @change="handleControllerModeChange">
              <el-option v-for="item in controllerModes" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <div class="subtle">当前模式由网关 + ROS2 状态回传决定，切换命令只在维护权限下开放。</div>
          </div>
        </div>

        <div class="button-stack">
          <el-button type="primary" :disabled="!safetyStore.canHomeRobot.allowed" :loading="systemStore.pendingCommand" @click="handleHome">执行回零</el-button>
          <el-button type="warning" :disabled="!safetyStore.canResetFault.allowed" :loading="systemStore.pendingCommand" @click="handleResetFault">故障复位</el-button>
          <el-button :disabled="!safetyStore.canRecover.allowed" :loading="systemStore.pendingCommand" @click="handleRecover">恢复到空闲</el-button>
          <el-button :disabled="!safetyStore.canControlGripper.allowed" :loading="robotStore.pendingCommand" @click="handleGripper(true)">打开夹爪</el-button>
          <el-button :disabled="!safetyStore.canControlGripper.allowed" :loading="robotStore.pendingCommand" @click="handleGripper(false)">闭合夹爪</el-button>
          <el-button :disabled="appStore.operatorRole !== 'maintainer'" @click="handleClearTargets">清空视觉目标缓存</el-button>
        </div>

        <div class="joint-card panel">
          <div class="panel-title">单关节点动</div>
          <div class="joint-form">
            <el-select v-model="jointIndex">
              <el-option v-for="item in jointOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-input-number v-model="stepDeg" :min="1" :max="effectiveManualCommandLimits.maxJogJointStepDeg" />
            <div class="jog-row">
              <el-button :disabled="!safetyStore.canJog.allowed" :loading="robotStore.pendingCommand" @click="handleJog(-1)">负向点动</el-button>
              <el-button type="primary" :disabled="!safetyStore.canJog.allowed" :loading="robotStore.pendingCommand" @click="handleJog(1)">正向点动</el-button>
            </div>
          </div>
        </div>

        <div class="joint-card panel">
          <div class="panel-title">笛卡尔微调</div>
          <div class="joint-form">
            <el-input-number v-model="servoStep" :min="1" :max="maxServoStepMm" />
            <div class="servo-grid">
              <el-button :disabled="!canServo" :loading="robotStore.pendingCommand" @click="handleServo('x', -servoDeltaMeters(servoStep))">X-</el-button>
              <el-button :disabled="!canServo" :loading="robotStore.pendingCommand" @click="handleServo('x', servoDeltaMeters(servoStep))">X+</el-button>
              <el-button :disabled="!canServo" :loading="robotStore.pendingCommand" @click="handleServo('y', -servoDeltaMeters(servoStep))">Y-</el-button>
              <el-button :disabled="!canServo" :loading="robotStore.pendingCommand" @click="handleServo('y', servoDeltaMeters(servoStep))">Y+</el-button>
              <el-button :disabled="!canServo" :loading="robotStore.pendingCommand" @click="handleServo('z', -servoDeltaMeters(servoStep))">Z-</el-button>
              <el-button :disabled="!canServo" :loading="robotStore.pendingCommand" @click="handleServo('z', servoDeltaMeters(servoStep))">Z+</el-button>
            </div>
            <div class="subtle">输入步长单位为 mm；发送到后端前会转换为 m。笛卡尔微调与关节点动已拆分独立门禁；伺服不再复用点动判定。</div>
          </div>
        </div>

        <div class="subtle note">当前门禁：{{ safetyStore.guardSummary }}</div>
      </div>

      <div class="right-column">
        <RobotStatusPanel />
        <section class="panel audit-panel">
          <div class="panel-title">运行时公开表面</div>
          <div class="data-list" style="margin-top: 12px">
            <div class="data-row"><span class="subtle">runtime</span><span>{{ readinessStore.runtimeSurfaceState?.runtimeLabel || '--' }}</span></div>
            <div class="data-row"><span class="subtle">badge</span><span>{{ readinessStore.runtimeSurfaceState?.runtimeBadge || '--' }}</span></div>
            <div class="data-row"><span class="subtle">公开命令平面</span><span>{{ (readinessStore.runtimeSurfaceState?.publicCommandPlanes || []).join(' / ') || '--' }}</span></div>
            <div class="data-row"><span class="subtle">观测平面</span><span>{{ (readinessStore.runtimeSurfaceState?.observabilityCommandPlanes || []).join(' / ') || '--' }}</span></div>
            <div class="data-row"><span class="subtle">delivery track</span><span>{{ readinessStore.runtimeSurfaceState?.runtimeDeliveryTrack || '--' }}</span></div>
            <div class="data-row"><span class="subtle">execution backbone</span><span>{{ readinessStore.runtimeSurfaceState?.effectiveExecutionBackbone || readinessStore.runtimeSurfaceState?.declaredExecutionBackbone || readinessStore.runtimeSurfaceState?.executionBackbone || '--' }}</span></div>
            <div class="data-row"><span class="subtle">declared backbone</span><span>{{ readinessStore.runtimeSurfaceState?.declaredExecutionBackbone || readinessStore.runtimeSurfaceState?.executionBackbone || '--' }}</span></div>
            <div class="data-row"><span class="subtle">统一入口</span><span>{{ (readinessStore.runtimeSurfaceState?.runtimeGatewayEntrypoints || []).join(' / ') || '--' }}</span></div>
            <div class="data-row"><span class="subtle">已激活 runtime interface</span><span>{{ (readinessStore.runtimeSurfaceState?.activeRuntimeInterfaces || []).join(' / ') || '--' }}</span></div>
            <div class="data-row"><span class="subtle">隐藏 runtime interface</span><span>{{ (readinessStore.runtimeSurfaceState?.hiddenRuntimeInterfaces || []).join(' / ') || '--' }}</span></div>
          </div>
        </section>

        <section class="panel audit-panel">
          <div class="panel-title">能力描述符</div>
          <el-table :data="capabilityDescriptorRows" style="margin-top: 12px" height="220">
            <el-table-column prop="name" label="能力" width="140" />
            <el-table-column prop="dataPlane" label="数据平面" width="140" />
            <el-table-column prop="controlPlane" label="控制平面" width="170" />
            <el-table-column prop="executionBinding" label="业务绑定" width="150" />
            <el-table-column prop="authorityLevel" label="权威级别" min-width="180" />
          </el-table>
        </section>

        <section class="panel audit-panel">
          <div class="panel-title">命令生命周期</div>
          <el-table :data="commandLifecycleStore.records" style="margin-top: 12px" height="280">
            <el-table-column prop="acceptedAt" label="受理时间" width="180" />
            <el-table-column prop="action" label="动作" width="160" />
            <el-table-column prop="status" label="阶段" width="100" />
            <el-table-column prop="completionPending" label="待终态" width="90">
              <template #default="scope">{{ scope.row.completionPending ? '是' : '否' }}</template>
            </el-table-column>
            <el-table-column prop="requestId" label="requestId" width="180" />
            <el-table-column prop="message" label="结果说明" min-width="240" />
          </el-table>
        </section>

        <section class="panel audit-panel">
          <div class="panel-title">命令审计</div>
          <el-table :data="auditStore.records" style="margin-top: 12px" height="360">
            <el-table-column prop="createdAt" label="时间" width="180" />
            <el-table-column prop="action" label="动作" width="160" />
            <el-table-column prop="actorRole" label="角色" width="100" />
            <el-table-column prop="status" label="状态" width="100" />
            <el-table-column prop="reason" label="结果说明" min-width="220" />
          </el-table>
        </section>

        <section class="panel audit-panel">
          <div class="panel-title">命令回执</div>
          <el-table :data="receiptStore.records" style="margin-top: 12px" height="280">
            <el-table-column prop="timestamp" label="时间" width="180" />
            <el-table-column prop="action" label="动作" width="160" />
            <el-table-column prop="commandPlane" label="平面" width="140" />
            <el-table-column prop="receiptClass" label="回执类" width="140" />
            <el-table-column prop="status" label="状态" width="100" />
            <el-table-column prop="message" label="结果说明" min-width="220" />
          </el-table>
        </section>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import RobotStatusPanel from '@/components/robot/RobotStatusPanel.vue';
import { CONTROLLER_MODE_OPTIONS } from '@/constants/system';
import { resolveControllerMode, type ControllerMode } from '@/models/system';
import { useSystemStore } from '@/stores/system';
import { useRobotStore } from '@/stores/robot';
import { useTaskStore } from '@/stores/task';
import { useSafetyStore } from '@/stores/safety';
import { useReadinessStore } from '@/stores/readiness';
import { useAuditStore } from '@/stores/audit';
import { useReceiptStore } from '@/stores/receipt';
import { useCommandLifecycleStore } from '@/stores/commandLifecycle';
import { useAppStore } from '@/stores/app';
import { useDangerConfirm } from '@/composables/useDangerConfirm';
import { useCommandBus } from '@/services/commands/commandBus';
import { MANUAL_COMMAND_LIMITS } from '@/generated/runtimeContract';
import { clearVisionTargets } from '@/services/api/vision';

const systemStore = useSystemStore();
const robotStore = useRobotStore();
const taskStore = useTaskStore();
const safetyStore = useSafetyStore();
const readinessStore = useReadinessStore();
const auditStore = useAuditStore();
const receiptStore = useReceiptStore();
const commandLifecycleStore = useCommandLifecycleStore();
const appStore = useAppStore();
const { confirmDanger } = useDangerConfirm();
const commandBus = useCommandBus();

const jointIndex = ref(0);
const stepDeg = ref(2);
const servoStep = ref(5);
const controllerModes = CONTROLLER_MODE_OPTIONS;
const controllerMode = computed<ControllerMode>(() => systemStore.current ? resolveControllerMode(systemStore.current as Record<string, unknown>) : 'idle');
const canServo = computed(() => safetyStore.canServoCartesian.allowed);
const effectiveManualCommandLimits = computed(() => readinessStore.manualCommandLimits || MANUAL_COMMAND_LIMITS);
const maxServoStepMm = computed(() => Math.round(effectiveManualCommandLimits.value.maxServoCartesianDeltaMeters * 1000));
const capabilityDescriptorRows = computed(() => Object.entries(readinessStore.capabilityDescriptors || {}).map(([name, payload]) => ({
  name,
  dataPlane: payload.data_plane,
  controlPlane: payload.control_plane,
  executionBinding: payload.execution_binding,
  authorityLevel: payload.authority_level,
})));

const previewNotice = computed(() => {
  if (robotStore.localPreviewOnly) return robotStore.localPreviewMessage || '当前维护命令仅做本地 preview 投影，未下发到权威运行时。';
  if (systemStore.localPreviewOnly) return systemStore.localPreviewMessage || '当前系统命令仅做本地 preview 投影，未下发到权威运行时。';
  if (taskStore.localPreviewOnly) return taskStore.localPreviewMessage || '当前任务命令仅做本地 preview 投影，未下发到权威运行时。';
  return '';
});

watch(effectiveManualCommandLimits, (limits) => {
  if (stepDeg.value > limits.maxJogJointStepDeg) stepDeg.value = limits.maxJogJointStepDeg;
  if (stepDeg.value < 1) stepDeg.value = 1;
  if (servoStep.value > maxServoStepMm.value) servoStep.value = maxServoStepMm.value;
  if (servoStep.value < 1) servoStep.value = 1;
}, { immediate: true });

function servoDeltaMeters(stepMm: number): number {
  const meters = stepMm / 1000;
  const limit = effectiveManualCommandLimits.value.maxServoCartesianDeltaMeters;
  return Math.min(Math.max(meters, -limit), limit);
}

function showCommandResult(successMessage: string, previewMessage: string) {
  ElMessage.success(robotStore.localPreviewOnly ? previewMessage : successMessage);
}

const jointOptions = Array.from({ length: 6 }).map((_, index) => ({
  label: `J${index + 1}`,
  value: index
}));

async function handleHome() {
  try {
    await confirmDanger('确认执行回零？');
    await commandBus.home();
    ElMessage.success(systemStore.localPreviewOnly ? '回零命令仅做本地 preview 投影' : '回零命令已受理');
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleResetFault() {
  try {
    await confirmDanger('确认执行故障复位？');
    await commandBus.resetFault();
    ElMessage.success(systemStore.localPreviewOnly ? '故障复位命令仅做本地 preview 投影' : '故障复位命令已受理');
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleRecover() {
  try {
    await confirmDanger('确认执行运行时恢复并回到空闲态？');
    await commandBus.recoverRuntime();
    ElMessage.success(systemStore.localPreviewOnly ? '运行时恢复命令仅做本地 preview 投影' : '运行时恢复命令已受理');
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleControllerModeChange(value: ControllerMode) {
  try {
    await confirmDanger(`确认切换控制器模式到 ${value}？`);
    await commandBus.setControllerMode(value);
    showCommandResult(`模式切换命令已受理：${value}`, `模式切换仅做本地 preview 投影：${value}`);
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleGripper(open: boolean) {
  try {
    await confirmDanger(open ? '确认打开夹爪？' : '确认闭合夹爪？');
    await commandBus.setGripper(open);
    showCommandResult(open ? '打开夹爪命令已受理' : '闭合夹爪命令已受理', open ? '打开夹爪仅做本地 preview 投影' : '闭合夹爪仅做本地 preview 投影');
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}


async function handleClearTargets() {
  try {
    await confirmDanger('确认清空当前视觉目标缓存？');
    await clearVisionTargets();
    ElMessage.success('已清空视觉目标缓存');
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleJog(direction: -1 | 1) {
  try {
    await confirmDanger(`确认对 J${jointIndex.value + 1} 执行${direction > 0 ? '正向' : '负向'}点动 ${stepDeg.value}°？`);
    await commandBus.jogJoint(jointIndex.value, direction, stepDeg.value);
    showCommandResult(`J${jointIndex.value + 1} ${direction > 0 ? '正向' : '负向'}点动命令已受理`, `J${jointIndex.value + 1} 点动仅做本地 preview 投影`);
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleServo(axis: string, delta: number) {
  try {
    const deltaMm = delta * 1000;
    await confirmDanger(`确认执行 ${axis.toUpperCase()} 轴 ${deltaMm > 0 ? '+' : ''}${deltaMm} mm 微调？`);
    await commandBus.servoCartesian(axis, delta);
    showCommandResult(`${axis.toUpperCase()} 轴微调命令已受理`, `${axis.toUpperCase()} 轴微调仅做本地 preview 投影`);
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}
</script>

<style scoped>
.maintenance-page { display: flex; flex-direction: column; gap: 16px; }
.action-panel, .audit-panel { padding: 16px; }
.mode-card { margin-top: 12px; padding: 14px; }
.button-stack { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }
.joint-card { margin-top: 16px; padding: 14px; }
.joint-form { margin-top: 12px; display: flex; flex-direction: column; gap: 12px; }
.jog-row, .servo-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.note { margin-top: 14px; }
.right-column { display: flex; flex-direction: column; gap: 16px; }
</style>
