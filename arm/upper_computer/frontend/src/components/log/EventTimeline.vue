<template>
  <section class="panel event-timeline">
    <div class="panel-head">
      <div>
        <div class="panel-title">Event Timeline</div>
        <div class="subtle">Latest runtime events</div>
      </div>
      <el-tag>{{ visibleRecords.length }}</el-tag>
    </div>

    <div v-if="visibleRecords.length" class="timeline-list">
      <div v-for="record in visibleRecords" :key="record.id" class="timeline-item">
        <span class="dot" :class="`level-${record.level}`"></span>
        <div class="timeline-content">
          <div class="timeline-main">
            <span class="event">{{ record.event }}</span>
            <span class="message">{{ record.message }}</span>
          </div>
          <div class="subtle meta">
            <span>{{ formatDateTime(record.timestamp) }}</span>
            <span>{{ record.module }}</span>
            <span v-if="record.requestId">req={{ record.requestId }}</span>
          </div>
        </div>
      </div>
    </div>
    <div v-else class="empty subtle">No events yet</div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { LogEvent } from '@/models/log';
import { formatDateTime } from '@/utils/format';

const props = withDefaults(
  defineProps<{
    records: LogEvent[];
    limit?: number;
  }>(),
  {
    limit: 10,
  }
);

const visibleRecords = computed(() => props.records.slice(0, Math.max(0, props.limit)));
</script>

<style scoped>
.event-timeline { padding: 16px; }
.panel-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.timeline-list { display: flex; flex-direction: column; gap: 12px; margin-top: 12px; }
.timeline-item { display: grid; grid-template-columns: 12px minmax(0, 1fr); gap: 10px; align-items: start; }
.dot { width: 9px; height: 9px; margin-top: 5px; border-radius: 999px; background: var(--success); box-shadow: 0 0 0 3px rgba(255,255,255,0.04); }
.timeline-content { min-width: 0; padding-bottom: 10px; border-bottom: 1px solid var(--line); }
.timeline-main { display: flex; gap: 8px; min-width: 0; }
.event { flex: 0 0 auto; font-weight: 700; }
.message { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); }
.meta { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 6px; font-size: 12px; }
.empty { margin-top: 12px; }
.level-warn { background: var(--warning); }
.level-error,
.level-fault { background: var(--danger); }
</style>
