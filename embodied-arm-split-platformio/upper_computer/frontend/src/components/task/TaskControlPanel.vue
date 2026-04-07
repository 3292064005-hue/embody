<template>
  <section class="panel task-control">
    <div class="panel-title">任务控制台</div>
    <div class="controls">
      <el-select v-model="selectedTemplateId" placeholder="选择任务模板">
        <el-option v-for="template in templates" :key="template.id" :label="template.name" :value="template.id" />
      </el-select>
      <el-input v-model="selectedTargetCategory" placeholder="目标类别，如 red / blue / green" />
      <div class="action-grid">
        <el-button type="primary" :disabled="!safetyStore.canStartTask.allowed" :loading="taskStore.pending" @click="handleStart">开始任务</el-button>
        <el-button type="warning" :disabled="!safetyStore.canStopTask.allowed || !taskStore.currentTask" :loading="taskStore.pending" @click="handleStop">停止</el-button>
        <el-button :disabled="!safetyStore.canHomeRobot.allowed" :loading="systemStore.pendingCommand" @click="handleHome">回零</el-button>
        <el-button type="danger" :disabled="!safetyStore.canResetFault.allowed" :loading="systemStore.pendingCommand" @click="handleResetFault">复位故障</el-button>
      </div>
    </div>
    <div class="subtle hint">当前门禁：{{ safetyStore.guardSummary }}</div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { useTaskStore } from '@/stores/task';
import { useSystemStore } from '@/stores/system';
import { useSafetyStore } from '@/stores/safety';
import { useDangerConfirm } from '@/composables/useDangerConfirm';
import { useCommandBus } from '@/services/commands/commandBus';

const taskStore = useTaskStore();
const systemStore = useSystemStore();
const safetyStore = useSafetyStore();
const { confirmDanger } = useDangerConfirm();
const commandBus = useCommandBus();

const selectedTemplateId = ref<string>('');
const selectedTargetCategory = ref<string>('red');
const templates = computed(() => taskStore.templates);

watch(
  templates,
  (value) => {
    if (value.length && !selectedTemplateId.value) {
      selectedTemplateId.value = value[0].id;
      selectedTargetCategory.value = value[0].defaultTargetCategory || 'red';
      taskStore.setSelectedTemplate(value[0].id);
    }
  },
  { immediate: true }
);

watch(selectedTemplateId, (value) => {
  taskStore.setSelectedTemplate(value);
  selectedTargetCategory.value = taskStore.currentTemplate?.defaultTargetCategory || selectedTargetCategory.value;
});

async function handleStart() {
  try {
    const template = taskStore.templates.find((item) => item.id === selectedTemplateId.value);
    if (!template) {
      ElMessage.warning('请先选择任务模板');
      return;
    }
    await confirmDanger(`确认启动任务：${template.name}？`, '操作确认');
    await commandBus.startTask({ taskType: template.taskType, targetCategory: selectedTargetCategory.value, templateId: template.id });
    ElMessage.success(`已发起任务：${template.name}`);
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleStop() {
  try {
    await confirmDanger('确认停止当前任务？', '操作确认');
    await commandBus.stopTask();
    ElMessage.success('已发送停止任务命令');
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleHome() {
  try {
    await confirmDanger('确认执行回零？', '操作确认');
    await commandBus.home();
    ElMessage.success('已发送回零命令');
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}

async function handleResetFault() {
  try {
    await confirmDanger('确认复位故障？', '操作确认');
    await commandBus.resetFault();
    ElMessage.success('已发送故障复位命令');
  } catch (error) {
    if (error instanceof Error) ElMessage.warning(error.message);
  }
}
</script>

<style scoped>
.task-control { padding: 16px; }
.controls { display: flex; flex-direction: column; gap: 14px; margin-top: 12px; }
.action-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.hint { margin-top: 14px; }
</style>
