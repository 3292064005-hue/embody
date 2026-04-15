<template>
  <section class="panel task-control">
    <div class="panel-title">任务控制台</div>
    <el-alert
      v-if="showPreviewRuntimeNotice"
      type="warning"
      :closable="false"
      class="preview-alert"
      title="当前 runtime 为 preview / contract-only 语义"
      description="任务入口仅用于能力验证与链路联调；需要 authoritative runtime lane 才能进入正式执行。"
    />
    <div class="controls">
      <template v-if="showTaskWorkbench">
        <el-select v-model="selectedTemplateId" placeholder="选择任务模板">
          <el-option v-for="template in templates" :key="template.id" :label="template.name" :value="template.id" />
        </el-select>
        <el-select v-if="currentTemplateTargetOptions.length" v-model="selectedTargetCategory" placeholder="选择目标类别">
          <el-option v-for="item in currentTemplateTargetOptions" :key="item" :label="item" :value="item" />
        </el-select>
        <div v-else class="subtle">当前模板不需要显式目标类别，placement 将按模板默认策略解析。</div>
        <div v-if="currentTemplate?.operatorHint" class="subtle template-hint">{{ currentTemplate.operatorHint }}</div>
        <div class="action-grid">
          <el-button type="primary" :disabled="!safetyStore.canStartTask.allowed" :loading="taskStore.pending" @click="handleStart">开始任务</el-button>
          <el-button type="warning" :disabled="!safetyStore.canStopTask.allowed || !taskStore.currentTask" :loading="taskStore.pending" @click="handleStop">停止</el-button>
          <el-button :disabled="!safetyStore.canHomeRobot.allowed" :loading="systemStore.pendingCommand" @click="handleHome">回零</el-button>
          <el-button type="danger" :disabled="!safetyStore.canResetFault.allowed" :loading="systemStore.pendingCommand" @click="handleResetFault">复位故障</el-button>
        </div>
      </template>
      <template v-else>
        <div class="preview-summary subtle">{{ runtimeFeatures.taskStartReason }}</div>
        <div class="action-grid reduced-grid">
          <el-button type="warning" :disabled="!safetyStore.canStopTask.allowed || !taskStore.currentTask" :loading="taskStore.pending" @click="handleStop">停止任务</el-button>
          <el-button :disabled="!safetyStore.canHomeRobot.allowed" :loading="systemStore.pendingCommand" @click="handleHome">回零</el-button>
          <el-button type="danger" :disabled="!safetyStore.canResetFault.allowed" :loading="systemStore.pendingCommand" @click="handleResetFault">复位故障</el-button>
        </div>
      </template>
    </div>
    <div class="subtle hint">任务门禁：{{ safetyStore.canStartTask.reason }} ｜ 全局摘要：{{ safetyStore.guardSummary }}</div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { useTaskStore } from '@/stores/task';
import { useSystemStore } from '@/stores/system';
import { useSafetyStore } from '@/stores/safety';
import { useReadinessStore } from '@/stores/readiness';
import { useDangerConfirm } from '@/composables/useDangerConfirm';
import { useCommandBus } from '@/services/commands/commandBus';
import { deriveRuntimeFeatureState } from '@/models/runtimeFeatures';
import type { TargetCategory } from '@/models/task';

const taskStore = useTaskStore();
const systemStore = useSystemStore();
const safetyStore = useSafetyStore();
const readinessStore = useReadinessStore();
const { confirmDanger } = useDangerConfirm();
const commandBus = useCommandBus();

const selectedTemplateId = ref<string>('');
const selectedTargetCategory = ref<TargetCategory>('red');
const templates = computed(() => taskStore.templates);
const currentTemplate = computed(() => taskStore.currentTemplate);
const currentTemplateTargetOptions = computed(() => currentTemplate.value?.allowedTargetCategories || []);
const runtimeFeatures = computed(() => deriveRuntimeFeatureState(readinessStore.$state));
const showPreviewRuntimeNotice = computed(() => runtimeFeatures.value.previewRuntime);
const showTaskWorkbench = computed(() => runtimeFeatures.value.taskWorkbenchVisible);

watch(
  templates,
  (value) => {
    if (value.length && !selectedTemplateId.value) {
      selectedTemplateId.value = value[0].id;
      const targetOptions = value[0].allowedTargetCategories || [];
      selectedTargetCategory.value = value[0].defaultTargetCategory || targetOptions[0] || ('red' as TargetCategory);
      taskStore.setSelectedTemplate(value[0].id);
    }
  },
  { immediate: true }
);

watch(selectedTemplateId, (value) => {
  taskStore.setSelectedTemplate(value);
  const template = taskStore.currentTemplate;
  const targetOptions = template?.allowedTargetCategories || [];
  selectedTargetCategory.value = template?.defaultTargetCategory || targetOptions[0] || selectedTargetCategory.value;
});

async function handleStart() {
  try {
    const template = taskStore.templates.find((item) => item.id === selectedTemplateId.value);
    if (!template) {
      ElMessage.warning('请先选择任务模板');
      return;
    }
    await confirmDanger(`确认启动任务：${template.name}？`, '操作确认');
    await commandBus.startTask({
      taskType: template.taskType,
      targetCategory: template.allowedTargetCategories?.length ? selectedTargetCategory.value : undefined,
      templateId: template.id
    });
    ElMessage.success(`已发起任务：${template.name}`);
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleStop() {
  try {
    await confirmDanger('确认停止当前任务？', '操作确认');
    await commandBus.stopTask();
    ElMessage.success(taskStore.localPreviewOnly ? '停止任务命令仅做本地 preview 投影' : '已发送停止任务命令');
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleHome() {
  try {
    await confirmDanger('确认执行回零？', '操作确认');
    await commandBus.home();
    ElMessage.success(systemStore.localPreviewOnly ? '回零命令仅做本地 preview 投影' : '已发送回零命令');
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleResetFault() {
  try {
    await confirmDanger('确认复位故障？', '操作确认');
    await commandBus.resetFault();
    ElMessage.success(systemStore.localPreviewOnly ? '故障复位命令仅做本地 preview 投影' : '已发送故障复位命令');
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}
</script>

<style scoped>
.task-control { padding: 16px; }
.controls { display: flex; flex-direction: column; gap: 14px; margin-top: 12px; }
.action-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.preview-alert { margin-top: 12px; }
.hint { margin-top: 14px; }
.preview-summary { line-height: 1.7; }
.reduced-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.template-hint { line-height: 1.6; }
</style>
