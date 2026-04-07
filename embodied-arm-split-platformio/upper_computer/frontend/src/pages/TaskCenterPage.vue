<template>
  <section class="task-page">
    <div class="grid-3 summary-grid">
      <MetricCard label="当前模板数" :value="taskStore.templates.length" hint="冻结任务入口数量" tone="success" />
      <MetricCard label="历史成功率" :value="`${taskStore.successRate}%`" hint="按历史任务统计" :tone="taskStore.successRate >= 80 ? 'success' : 'warning'" />
      <MetricCard label="当前阶段" :value="taskStore.currentTask?.stage || 'idle'" hint="只读降级与审计链已纳入运行时" :tone="taskStore.currentTask ? 'warning' : 'success'" />
    </div>

    <div class="panel page-panel">
      <div class="header-row">
        <div>
          <div class="panel-title">任务中心</div>
          <div class="subtle">模板、执行策略、历史任务与审计友好的发令入口</div>
        </div>
      </div>
      <div class="grid-2 content-grid">
        <div class="panel inner-panel">
          <div class="panel-title">任务模板</div>
          <el-table :data="taskStore.templates" style="margin-top: 12px" height="320" highlight-current-row @row-click="handleTemplateRowClick">
            <el-table-column prop="name" label="模板名称" min-width="180" />
            <el-table-column prop="taskType" label="任务类型" width="140" />
            <el-table-column prop="riskLevel" label="风险等级" width="120" />
            <el-table-column prop="description" label="说明" min-width="220" />
          </el-table>
          <div class="subtle" style="margin-top: 10px">当前选择：{{ taskStore.currentTemplate?.name || '--' }}</div>
        </div>
        <div class="panel inner-panel">
          <div class="panel-title">执行策略建议</div>
          <ul class="bullet-list subtle">
            <li>任务启动前显式确认模板与目标类别，避免误抓。</li>
            <li>批处理任务必须输出批次汇总与失败明细。</li>
            <li>故障态、只读降级态、未回零态均禁止启动新任务。</li>
            <li>任务停止、回零、急停等动作均进入命令审计链。</li>
          </ul>
        </div>
      </div>
    </div>

    <div class="panel page-panel">
      <div class="panel-title">历史任务</div>
      <el-table :data="taskStore.history" style="margin-top: 12px" height="320">
        <el-table-column prop="taskId" label="任务 ID" width="180" />
        <el-table-column prop="taskType" label="类型" width="140" />
        <el-table-column prop="success" label="结果" width="100">
          <template #default="scope">
            <el-tag :type="scope.row.success ? 'success' : 'danger'">{{ scope.row.success ? '成功' : '失败' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="retryCount" label="重试" width="80" />
        <el-table-column prop="durationMs" label="耗时" width="120">
          <template #default="scope">{{ formatDuration(scope.row.durationMs) }}</template>
        </el-table-column>
        <el-table-column prop="resultMessage" label="结果说明" min-width="240" />
      </el-table>
    </div>
  </section>
</template>

<script setup lang="ts">
import MetricCard from '@/components/common/MetricCard.vue';
import { useTaskStore } from '@/stores/task';
import { formatDuration } from '@/utils/format';
import type { TaskTemplate } from '@/models/task';

const taskStore = useTaskStore();

function handleTemplateRowClick(row: TaskTemplate) {
  taskStore.setSelectedTemplate(row.id);
}
</script>

<style scoped>
.task-page { display: flex; flex-direction: column; gap: 16px; }
.summary-grid { margin-bottom: 2px; }
.page-panel { padding: 18px; }
.content-grid { margin-top: 16px; }
.inner-panel { padding: 16px; }
.bullet-list { margin: 14px 0 0; padding-left: 18px; line-height: 1.8; }
</style>
