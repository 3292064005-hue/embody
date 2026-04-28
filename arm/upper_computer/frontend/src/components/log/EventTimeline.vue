<template>
  <section class="panel event-timeline">
    <div class="header-row">
      <div>
        <div class="panel-title">事件流</div>
        <div class="subtle">最近 {{ visibleRecords.length }} 条运行事件</div>
      </div>
    </div>

    <div v-if="visibleRecords.length" class="timeline">
      <article v-for="item in visibleRecords" :key="item.id" class="timeline-item">
        <span class="marker" :class="`marker-${item.level}`"></span>
        <div class="event-body">
          <div class="event-topline">
            <span class="event-name">{{ item.event }}</span>
            <span class="subtle">{{ formatDateTime(item.timestamp) }}</span>
          </div>
          <div class="event-message">{{ item.message }}</div>
          <div class="subtle event-meta">
            {{ item.module }}
            <span v-if="item.taskId"> / task={{ item.taskId }}</span>
            <span v-if="item.requestId"> / request={{ item.requestId }}</span>
          </div>
        </div>
      </article>
    </div>
    <div v-else class="empty subtle">等待网关日志。</div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { LogEvent } from '@/models/log';
import { formatDateTime } from '@/utils/format';

const props = withDefaults(defineProps<{
  records: LogEvent[];
  limit?: number;
}>(), {
  limit: 10
});

const visibleRecords = computed(() => props.records.slice(0, props.limit));
</script>

<style scoped>
.event-timeline { padding: 16px; }
.header-row { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.timeline { display: flex; flex-direction: column; gap: 12px; margin-top: 14px; }
.timeline-item { display: grid; grid-template-columns: 12px minmax(0, 1fr); gap: 10px; }
.marker { width: 10px; height: 10px; margin-top: 5px; border-radius: 50%; background: var(--safe); }
.marker-info { background: var(--accent); }
.marker-warn { background: var(--warning); }
.marker-error, .marker-fault { background: var(--danger); }
.event-body { min-width: 0; border-bottom: 1px dashed rgba(142, 160, 186, 0.18); padding-bottom: 12px; }
.timeline-item:last-child .event-body { border-bottom: none; padding-bottom: 0; }
.event-topline { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; }
.event-name { font-weight: 700; overflow-wrap: anywhere; }
.event-message { margin-top: 6px; line-height: 1.5; overflow-wrap: anywhere; }
.event-meta { margin-top: 6px; font-size: 12px; overflow-wrap: anywhere; }
.empty { margin-top: 14px; line-height: 1.6; }
</style>
