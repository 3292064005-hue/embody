<template>
  <section class="task-page">
    <div class="grid-4 summary-grid">
      <MetricCard label="任务工作台" :value="runtimeFeatures.runtimeBadge" :hint="runtimeFeatures.taskStartReason" :tone="runtimeFeatures.taskWorkbenchVisible ? 'success' : 'warning'" />
      <MetricCard label="执行背板" :value="executionBackboneLabel" :hint="executionModeLabel" :tone="readinessStore.executionBackboneSummary?.authoritativeTransport ? 'success' : 'warning'" />
      <MetricCard label="历史成功率" :value="`${taskStore.successRate}%`" hint="按历史任务统计" :tone="taskStore.successRate >= 80 ? 'success' : 'warning'" />
      <MetricCard label="当前阶段" :value="taskStore.currentTask?.stage || 'idle'" :hint="runtimeFeatures.runtimeLabel" :tone="taskStore.currentTask ? 'warning' : 'success'" />
    </div>

    <el-alert
      v-if="runtimeFeatures.previewRuntime || !runtimeFeatures.taskExecutionInteractive"
      type="warning"
      :closable="false"
      class="page-alert"
      :title="runtimeFeatures.previewRuntime ? '任务工作台已按 capability 收口为只读' : '任务工作台已开放，但当前发令仍受限'"
      :description="runtimeFeatures.taskStartReason"
    />

    <div class="grid-2 content-grid">
      <div class="panel page-panel">
        <div class="panel-title">运行时收口</div>
        <div class="meta-grid" style="margin-top: 12px">
          <div><strong>delivery track：</strong>{{ readinessStore.runtimeDeliveryTrack || '--' }}</div>
          <div><strong>runtime profile：</strong>{{ readinessStore.executionBackboneSummary?.requestedRuntimeProfile || '--' }}</div>
          <div><strong>active lane：</strong>{{ readinessStore.executionBackboneSummary?.activeRuntimeLane || '--' }}</div>
          <div><strong>firmware profile：</strong>{{ readinessStore.firmwareSemanticProfile || '--' }}</div>
        </div>
        <div class="subtle" style="margin-top: 10px">{{ readinessStore.firmwareSemanticMessage || '固件语义未上报。' }}</div>
      </div>
      <div class="panel page-panel">
        <div class="panel-title">validated_live gate</div>
        <div class="gate-grid" style="margin-top: 12px">
          <div><strong>repo：</strong>{{ readinessStore.releaseGates?.repoGate || 'not_executed' }}</div>
          <div><strong>target：</strong>{{ readinessStore.releaseGates?.targetGate || 'not_executed' }}</div>
          <div><strong>HIL：</strong>{{ readinessStore.releaseGates?.hilGate || 'not_executed' }}</div>
          <div><strong>checklist：</strong>{{ readinessStore.releaseGates?.releaseChecklistGate || 'not_executed' }}</div>
          <div class="gate-wide"><strong>release：</strong>{{ readinessStore.releaseGates?.releaseGate || 'not_executed' }}</div>
        </div>
        <div v-if="runtimeFeatures.promotionControlled && runtimeFeatures.promotionMissing.length" class="subtle" style="margin-top: 10px">
          缺失项：{{ runtimeFeatures.promotionMissing.join(' / ') }}
        </div>
      </div>
    </div>

    <div v-if="runtimeFeatures.taskWorkbenchVisible" class="panel page-panel">
      <div v-if="runtimeFeatures.promotionControlled && !runtimeFeatures.promotionEffective" class="subtle page-note">当前产品线受 promotion receipt 治理，未生效前仅允许只读展示。</div>
      <div class="header-row">
        <div>
          <div class="panel-title">任务中心</div>
          <div class="subtle">模板、执行策略、任务图与审计友好的发令入口</div>
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
          <div class="panel-title">任务图</div>
          <div v-if="taskStore.currentTemplate?.taskGraph" class="task-graph">
            <div class="subtle">graphKey：{{ taskStore.currentTemplate?.taskGraph?.graphKey }}</div>
            <ol class="bullet-list subtle ordered-list">
              <li v-for="node in taskStore.currentTemplate?.taskGraph?.nodes || []" :key="node.id">
                <strong>{{ node.label }}</strong>
                <span class="node-meta">{{ node.kind }} / {{ node.id }}</span>
              </li>
            </ol>
            <div class="subtle">恢复策略：{{ taskStore.currentTemplate?.taskGraph?.recoveryPolicy?.mode || '--' }}</div>
          </div>
          <div v-else class="subtle" style="margin-top: 12px">当前模板未暴露任务图。</div>
        </div>
      </div>
    </div>

    <div class="panel page-panel">
      <div class="panel-title">历史任务</div>
      <div v-if="runtimeFeatures.previewRuntime || !runtimeFeatures.taskExecutionInteractive" class="subtle page-note">当前只开放历史与审计信息；任务模板和发令工作台仅在 authoritative runtime 中暴露。</div>
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
import { computed } from 'vue';
import MetricCard from '@/components/common/MetricCard.vue';
import { useTaskStore } from '@/stores/task';
import { useReadinessStore } from '@/stores/readiness';
import { formatDuration } from '@/utils/format';
import type { TaskTemplate } from '@/models/task';
import { deriveRuntimeFeatureState } from '@/models/runtimeFeatures';

const taskStore = useTaskStore();
const readinessStore = useReadinessStore();
const runtimeFeatures = computed(() => deriveRuntimeFeatureState(readinessStore.$state));
const executionBackboneLabel = computed(() => readinessStore.executionBackboneSummary?.backboneLabel || 'Unknown Backbone');
const executionModeLabel = computed(() => readinessStore.executionBackboneSummary?.executionModeLabel || readinessStore.executionBackboneSummary?.executionMode || '--');

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
.ordered-list { list-style: decimal; }
.page-alert { margin-bottom: 4px; }
.page-note { margin-top: 10px; line-height: 1.7; }
.meta-grid, .gate-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 16px; }
.gate-wide { grid-column: 1 / -1; }
.node-meta { margin-left: 8px; opacity: 0.7; }
</style>
