<template>
  <section class="panel alarm-panel">
    <div class="header-row">
      <div>
        <div class="panel-title">告警</div>
        <div class="subtle">最近故障与错误</div>
      </div>
      <span class="status-pill" :class="statusClass">
        <span class="status-dot"></span>
        {{ alarmCount }}
      </span>
    </div>

    <div v-if="latestAlarms.length" class="alarm-list">
      <article v-for="item in latestAlarms" :key="item.id" class="alarm-item">
        <div class="alarm-meta">
          <span class="level" :class="`level-${item.level}`">{{ item.level }}</span>
          <span class="subtle">{{ formatDateTime(item.timestamp) }}</span>
        </div>
        <div class="message">{{ item.message }}</div>
        <div class="subtle source">{{ item.module }} / {{ item.event }}</div>
      </article>
    </div>
    <div v-else class="empty subtle">当前没有故障告警。</div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useLogStore } from '@/stores/log';
import { formatDateTime } from '@/utils/format';

const logStore = useLogStore();

const latestAlarms = computed(() => logStore.records
  .filter((item) => item.level === 'fault' || item.level === 'error')
  .slice(0, 4));

const alarmCount = computed(() => latestAlarms.value.length);
const statusClass = computed(() => (alarmCount.value > 0 ? 'status-danger' : 'status-ok'));
</script>

<style scoped>
.alarm-panel { padding: 16px; }
.header-row { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.alarm-list { display: flex; flex-direction: column; gap: 10px; margin-top: 14px; }
.alarm-item { border: 1px solid rgba(142, 160, 186, 0.2); border-radius: 8px; padding: 10px; background: rgba(255, 255, 255, 0.02); }
.alarm-meta { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; }
.level { font-weight: 700; text-transform: uppercase; }
.level-error, .level-fault { color: var(--danger); }
.message { margin-top: 8px; line-height: 1.5; }
.source { margin-top: 6px; font-size: 12px; overflow-wrap: anywhere; }
.empty { margin-top: 14px; line-height: 1.6; }
</style>
