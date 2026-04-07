<template>
  <section class="logs-page">
    <div class="panel page-panel">
      <div class="header-row">
        <div>
          <div class="panel-title">日志与审计</div>
          <div class="subtle">统一展示日志、requestId / correlationId 链路以及网关审计记录。</div>
        </div>
        <el-button @click="logStore.exportFiltered">导出筛选日志</el-button>
      </div>

      <div class="diagnostics-strip panel inner-panel">
        <div class="panel-title">诊断摘要</div>
        <div class="diag-grid subtle">
          <span>ready={{ diagnosticsStore.ready ? 'yes' : 'no' }}</span>
          <span>degraded={{ diagnosticsStore.degraded ? 'yes' : 'no' }}</span>
          <span>latency={{ diagnosticsStore.latencyMs ?? '--' }} ms</span>
          <span>successRate={{ diagnosticsStore.taskSuccessRate ?? '--' }}%</span>
          <span>faultCount={{ diagnosticsStore.faultCount }}</span>
          <span>{{ diagnosticsStore.detail }}</span>
        </div>
      </div>

      <div class="filters-row">
        <el-select class="filter-item" :model-value="logStore.levelFilter" @change="logStore.setLevelFilter">
          <el-option v-for="item in levelOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-input class="filter-item" :model-value="logStore.taskIdFilter" placeholder="按 taskId 筛选" clearable @input="logStore.setTaskIdFilter(String($event))" />
        <el-input class="filter-item" :model-value="logStore.requestIdFilter" placeholder="按 requestId 筛选" clearable @input="logStore.setRequestIdFilter(String($event))" />
        <el-input class="filter-item" :model-value="logStore.correlationIdFilter" placeholder="按 correlationId 筛选" clearable @input="logStore.setCorrelationIdFilter(String($event))" />
        <el-input class="filter-item wide" :model-value="logStore.searchText" placeholder="搜索消息 / 模块 / 事件" clearable @input="logStore.setSearchText(String($event))" />
      </div>

      <div class="content-grid">
        <div class="table-col panel inner-panel">
          <div class="panel-title">事件日志</div>
          <el-table :data="logStore.filteredRecords" style="margin-top: 12px" height="320" @row-click="handleRowClick">
            <el-table-column prop="timestamp" label="时间" width="180">
              <template #default="scope">{{ formatDateTime(scope.row.timestamp) }}</template>
            </el-table-column>
            <el-table-column prop="level" label="级别" width="90" />
            <el-table-column prop="module" label="模块" width="180" />
            <el-table-column prop="event" label="事件" width="160" />
            <el-table-column prop="message" label="消息" min-width="260" />
          </el-table>
        </div>
        <div class="detail-col panel inner-panel">
          <div class="panel-title">记录详情</div>
          <div v-if="logStore.selectedRecord" class="data-list detail-content">
            <div class="data-row"><span class="subtle">时间</span><span>{{ formatDateTime(logStore.selectedRecord.timestamp) }}</span></div>
            <div class="data-row"><span class="subtle">级别</span><span>{{ logStore.selectedRecord.level }}</span></div>
            <div class="data-row"><span class="subtle">模块</span><span>{{ logStore.selectedRecord.module }}</span></div>
            <div class="data-row"><span class="subtle">事件</span><span>{{ logStore.selectedRecord.event }}</span></div>
            <div class="data-row"><span class="subtle">任务 ID</span><span>{{ logStore.selectedRecord.taskId || '--' }}</span></div>
            <div class="data-row"><span class="subtle">requestId</span><span>{{ logStore.selectedRecord.requestId || '--' }}</span></div>
            <div class="data-row"><span class="subtle">correlationId</span><span>{{ logStore.selectedRecord.correlationId || '--' }}</span></div>
            <div class="data-row"><span class="subtle">消息</span><span>{{ logStore.selectedRecord.message }}</span></div>
            <div class="payload-block">
              <div class="subtle">Payload</div>
              <pre>{{ JSON.stringify(logStore.selectedRecord.payload || {}, null, 2) }}</pre>
            </div>
          </div>
          <div v-else class="subtle detail-content">请选择一条日志记录查看详情。</div>
        </div>
      </div>

      <section class="panel inner-panel audit-section">
        <div class="panel-title">命令审计</div>
        <el-table :data="auditStore.records" style="margin-top: 12px" height="280">
          <el-table-column prop="createdAt" label="时间" width="180">
            <template #default="scope">{{ formatDateTime(scope.row.createdAt) }}</template>
          </el-table-column>
          <el-table-column prop="action" label="动作" width="180" />
          <el-table-column prop="actorRole" label="角色" width="100" />
          <el-table-column prop="status" label="状态" width="110" />
          <el-table-column prop="requestId" label="requestId" width="180" />
          <el-table-column prop="correlationId" label="correlationId" width="180" />
          <el-table-column prop="reason" label="结果说明" min-width="240" />
        </el-table>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { LOG_LEVEL_OPTIONS } from '@/constants/system';
import { useLogStore } from '@/stores/log';
import { useAuditStore } from '@/stores/audit';
import { useDiagnosticsStore } from '@/stores/diagnostics';
import { formatDateTime } from '@/utils/format';
import type { LogEvent } from '@/models/log';

const logStore = useLogStore();
const auditStore = useAuditStore();
const diagnosticsStore = useDiagnosticsStore();
const levelOptions = LOG_LEVEL_OPTIONS;

function handleRowClick(row: LogEvent) {
  logStore.setSelectedRecord(row.id);
}
</script>

<style scoped>
.logs-page { display: flex; flex-direction: column; gap: 16px; }
.page-panel { padding: 16px; }
.header-row { display: flex; justify-content: space-between; gap: 12px; }
.diagnostics-strip { margin-top: 14px; }
.diag-grid { margin-top: 10px; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.filters-row { display: grid; grid-template-columns: 180px 180px 180px 180px minmax(0, 1fr); gap: 12px; margin-top: 16px; }
.filter-item { width: 100%; }
.wide { min-width: 0; }
.content-grid { display: grid; grid-template-columns: minmax(0, 1.2fr) 360px; gap: 16px; margin-top: 12px; }
.inner-panel { padding: 16px; }
.detail-content { margin-top: 12px; }
.audit-section { margin-top: 16px; }
.payload-block { margin-top: 12px; }
.payload-block pre { margin: 8px 0 0; padding: 12px; border-radius: 12px; background: rgba(255,255,255,0.03); overflow: auto; max-height: 280px; }
</style>
