<template>
  <section class="panel health-panel">
    <div class="panel-head">
      <div>
        <div class="panel-title">连接健康</div>
        <div class="subtle">实时链路、同步链路与只读降级状态汇总</div>
      </div>
      <el-tag :type="tagType">{{ connectionStore.quality.toUpperCase() }}</el-tag>
    </div>
    <div class="data-list content">
      <div class="data-row"><span class="subtle">WS 状态</span><span>{{ connectionStore.wsState }}</span></div>
      <div class="data-row"><span class="subtle">网关在线</span><span>{{ connectionStore.gatewayConnected ? '是' : '否' }}</span></div>
      <div class="data-row"><span class="subtle">实时延迟</span><span>{{ formatLatency(connectionStore.latencyMs) }}</span></div>
      <div class="data-row"><span class="subtle">最近消息</span><span>{{ formatDateTime(connectionStore.lastMessageAt) }}</span></div>
      <div class="data-row"><span class="subtle">最近 PONG</span><span>{{ formatDateTime(connectionStore.lastPongAt) }}</span></div>
      <div class="data-row"><span class="subtle">最近同步</span><span>{{ formatDateTime(connectionStore.lastServerSyncAt) }}</span></div>
      <div class="data-row"><span class="subtle">最近事件</span><span>{{ connectionStore.lastEventName || '--' }}</span></div>
      <div class="data-row"><span class="subtle">重连次数</span><span>{{ connectionStore.reconnectAttempts }}</span></div>
      <div class="data-row"><span class="subtle">解析错误</span><span>{{ connectionStore.parseErrors }}</span></div>
      <div class="data-row"><span class="subtle">同步错误</span><span>{{ connectionStore.syncErrors }}</span></div>
      <div class="data-row"><span class="subtle">过期判定</span><span>{{ connectionStore.isRealtimeStale ? '已过期' : '正常' }}</span></div>
      <div class="data-row"><span class="subtle">控制模式</span><span>{{ connectionStore.readonlyDegraded ? '只读降级' : '正常可控' }}</span></div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useConnectionStore } from '@/stores/connection';
import { formatDateTime, formatLatency } from '@/utils/format';

const connectionStore = useConnectionStore();
const tagType = computed(() => connectionStore.quality === 'offline' ? 'danger' : connectionStore.quality === 'degraded' ? 'warning' : 'success');
</script>

<style scoped>
.health-panel { padding: 16px; }
.panel-head { display: flex; justify-content: space-between; gap: 12px; }
.content { margin-top: 12px; }
</style>
