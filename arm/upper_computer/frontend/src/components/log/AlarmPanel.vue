<template>
  <section class="panel alarm-panel">
    <div class="panel-head">
      <div>
        <div class="panel-title">Alarms</div>
        <div class="subtle">Recent warning, error, and fault events</div>
      </div>
      <el-tag :type="tagType">{{ alarmRecords.length }}</el-tag>
    </div>

    <div v-if="alarmRecords.length" class="alarm-list">
      <div v-for="record in alarmRecords" :key="record.id" class="alarm-item" :class="`level-${record.level}`">
        <div class="alarm-main">
          <span class="level">{{ record.level.toUpperCase() }}</span>
          <span class="message">{{ record.message || record.event }}</span>
        </div>
        <div class="subtle meta">
          <span>{{ formatDateTime(record.timestamp) }}</span>
          <span>{{ record.module }}</span>
        </div>
      </div>
    </div>
    <div v-else class="empty subtle">No active alarms</div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useLogStore } from '@/stores/log';
import { formatDateTime } from '@/utils/format';

const logStore = useLogStore();
const alarmRecords = computed(() => logStore.records.filter((item) => ['warn', 'error', 'fault'].includes(item.level)).slice(0, 6));
const tagType = computed(() => alarmRecords.value.some((item) => item.level === 'fault' || item.level === 'error') ? 'danger' : alarmRecords.value.length ? 'warning' : 'success');
</script>

<style scoped>
.alarm-panel { padding: 16px; }
.panel-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.alarm-list { display: flex; flex-direction: column; gap: 10px; margin-top: 12px; }
.alarm-item { padding: 10px 12px; border: 1px solid var(--line); border-left-width: 4px; border-radius: 8px; background: rgba(255,255,255,0.02); }
.alarm-main { display: flex; gap: 8px; align-items: baseline; min-width: 0; }
.level { flex: 0 0 auto; font-size: 11px; font-weight: 800; color: var(--text-dim); }
.message { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meta { display: flex; gap: 10px; margin-top: 6px; font-size: 12px; }
.empty { margin-top: 12px; }
.level-warn { border-left-color: var(--warning); }
.level-error,
.level-fault { border-left-color: var(--danger); }
</style>
