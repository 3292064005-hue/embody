<template>
  <section class="panel current-task">
    <div class="panel-title">当前任务摘要</div>
    <div v-if="taskStore.currentTask" class="data-list content">
      <div class="data-row"><span class="subtle">任务 ID</span><span>{{ taskStore.currentTask.taskId }}</span></div>
      <div class="data-row"><span class="subtle">任务类型</span><span>{{ taskStore.currentTask.taskType }}</span></div>
      <div class="data-row"><span class="subtle">当前阶段</span><span>{{ taskStore.currentTask.stage }}</span></div>
      <div class="data-row"><span class="subtle">完成度</span><span>{{ formatPercent(taskStore.currentTask.percent) }}</span></div>
      <div class="data-row"><span class="subtle">重试次数</span><span>{{ taskStore.currentTask.retryCount }}</span></div>
      <div class="data-row"><span class="subtle">目标类别</span><span>{{ taskStore.currentTask.targetCategory || '--' }}</span></div>
      <div class="data-row"><span class="subtle">最近消息</span><span>{{ taskStore.currentTask.lastMessage || '--' }}</span></div>
      <div class="data-row"><span class="subtle">最近更新</span><span>{{ formatDateTime(taskStore.currentTask.updatedAt) }}</span></div>
    </div>
    <div v-else class="empty subtle">暂无执行任务</div>
  </section>
</template>

<script setup lang="ts">
import { useTaskStore } from '@/stores/task';
import { formatDateTime, formatPercent } from '@/utils/format';

const taskStore = useTaskStore();
</script>

<style scoped>
.current-task {
  padding: 16px;
}

.content {
  margin-top: 12px;
}

.empty {
  padding: 24px 0 8px;
}
</style>
