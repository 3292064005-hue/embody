<template>
  <section class="maintenance-page">
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
          <el-button :disabled="!safetyStore.canControlGripper.allowed" :loading="robotStore.pendingCommand" @click="handleGripper(true)">打开夹爪</el-button>
          <el-button :disabled="!safetyStore.canControlGripper.allowed" :loading="robotStore.pendingCommand" @click="handleGripper(false)">闭合夹爪</el-button>
        </div>

        <div class="joint-card panel">
          <div class="panel-title">单关节点动</div>
          <div class="joint-form">
            <el-select v-model="jointIndex">
              <el-option v-for="item in jointOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <el-input-number v-model="stepDeg" :min="1" :max="15" />
            <div class="jog-row">
              <el-button :disabled="!safetyStore.canJog.allowed" :loading="robotStore.pendingCommand" @click="handleJog(-1)">负向点动</el-button>
              <el-button type="primary" :disabled="!safetyStore.canJog.allowed" :loading="robotStore.pendingCommand" @click="handleJog(1)">正向点动</el-button>
            </div>
          </div>
        </div>

        <div class="joint-card panel">
          <div class="panel-title">笛卡尔微调</div>
          <div class="joint-form">
            <el-input-number v-model="servoStep" :min="1" :max="20" />
            <div class="servo-grid">
              <el-button :disabled="!canServo" :loading="robotStore.pendingCommand" @click="handleServo('x', -servoStep / 1000)">X-</el-button>
              <el-button :disabled="!canServo" :loading="robotStore.pendingCommand" @click="handleServo('x', servoStep / 1000)">X+</el-button>
              <el-button :disabled="!canServo" :loading="robotStore.pendingCommand" @click="handleServo('y', -servoStep / 1000)">Y-</el-button>
              <el-button :disabled="!canServo" :loading="robotStore.pendingCommand" @click="handleServo('y', servoStep / 1000)">Y+</el-button>
              <el-button :disabled="!canServo" :loading="robotStore.pendingCommand" @click="handleServo('z', -servoStep / 1000)">Z-</el-button>
              <el-button :disabled="!canServo" :loading="robotStore.pendingCommand" @click="handleServo('z', servoStep / 1000)">Z+</el-button>
            </div>
            <div class="subtle">笛卡尔微调已进入正式维护链，仍受后端 readiness / mode / role 三重门禁控制。</div>
          </div>
        </div>

        <div class="subtle note">当前门禁：{{ safetyStore.guardSummary }}</div>
      </div>

      <div class="right-column">
        <RobotStatusPanel />
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
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { ElMessage } from 'element-plus';
import RobotStatusPanel from '@/components/robot/RobotStatusPanel.vue';
import { CONTROLLER_MODE_OPTIONS } from '@/constants/system';
import { resolveControllerMode, type ControllerMode } from '@/models/system';
import { useSystemStore } from '@/stores/system';
import { useRobotStore } from '@/stores/robot';
import { useSafetyStore } from '@/stores/safety';
import { useAuditStore } from '@/stores/audit';
import { useAppStore } from '@/stores/app';
import { useDangerConfirm } from '@/composables/useDangerConfirm';
import { useCommandBus } from '@/services/commands/commandBus';

const systemStore = useSystemStore();
const robotStore = useRobotStore();
const safetyStore = useSafetyStore();
const auditStore = useAuditStore();
const appStore = useAppStore();
const { confirmDanger } = useDangerConfirm();
const commandBus = useCommandBus();

const jointIndex = ref(0);
const stepDeg = ref(2);
const servoStep = ref(5);
const controllerModes = CONTROLLER_MODE_OPTIONS;
const controllerMode = computed<ControllerMode>(() => systemStore.current ? resolveControllerMode(systemStore.current as Record<string, unknown>) : 'idle');
const canServo = computed(() => Boolean(safetyStore.snapshot.commandPolicies?.servoCartesian?.allowed && safetyStore.canJog.allowed));

const jointOptions = Array.from({ length: 5 }).map((_, index) => ({
  label: `J${index + 1}`,
  value: index
}));

async function handleHome() {
  try {
    await confirmDanger('确认执行回零？');
    await commandBus.home();
    ElMessage.success('已发送回零命令');
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleResetFault() {
  try {
    await confirmDanger('确认执行故障复位？');
    await commandBus.resetFault();
    ElMessage.success('已发送故障复位命令');
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleControllerModeChange(value: ControllerMode) {
  try {
    await confirmDanger(`确认切换控制器模式到 ${value}？`);
    await commandBus.setControllerMode(value);
    ElMessage.success(`已发送模式切换命令：${value}`);
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleGripper(open: boolean) {
  try {
    await confirmDanger(open ? '确认打开夹爪？' : '确认闭合夹爪？');
    await commandBus.setGripper(open);
    ElMessage.success(open ? '已发送打开夹爪命令' : '已发送闭合夹爪命令');
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleJog(direction: -1 | 1) {
  try {
    await confirmDanger(`确认对 J${jointIndex.value + 1} 执行${direction > 0 ? '正向' : '负向'}点动 ${stepDeg.value}°？`);
    await commandBus.jogJoint(jointIndex.value, direction, stepDeg.value);
    ElMessage.success(`已发送 J${jointIndex.value + 1} ${direction > 0 ? '正向' : '负向'}点动命令`);
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleServo(axis: string, delta: number) {
  try {
    await confirmDanger(`确认执行 ${axis.toUpperCase()} 轴 ${delta > 0 ? '+' : ''}${delta} mm 微调？`);
    await commandBus.servoCartesian(axis, delta);
    ElMessage.success(`已发送 ${axis.toUpperCase()} 轴微调命令`);
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
