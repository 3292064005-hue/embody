<template>
  <div class="page-shell app-layout">
    <TopStatusBar />
    <div class="layout-body">
      <SideNav />
      <main class="main-view">
        <RouterView />
      </main>
      <aside class="quick-sidebar">
        <SafetyGuardBanner />
        <CurrentTaskSummary />
        <ConnectionHealthPanel />
        <AlarmPanel />
      </aside>
    </div>
    <footer class="footer-bar">
      <span>Gateway：{{ connectionStore.gatewayConnected ? '在线' : '离线' }}</span>
      <span>最近心跳：{{ formatDateTime(connectionStore.lastHeartbeatAt) }}</span>
      <span>最近同步：{{ formatDateTime(connectionStore.lastServerSyncAt) }}</span>
      <span>链路质量：{{ connectionStore.quality }}</span>
      <span>UI 状态：{{ connectionStore.readonlyDegraded ? '只读降级' : '可控' }}</span>
      <span>角色：{{ appStore.operatorRole }}</span>
      <span>系统时间戳：{{ formatDateTime(systemStore.systemTimestamp) }}</span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue';
import TopStatusBar from '@/components/system/TopStatusBar.vue';
import SideNav from '@/components/system/SideNav.vue';
import CurrentTaskSummary from '@/components/task/CurrentTaskSummary.vue';
import AlarmPanel from '@/components/log/AlarmPanel.vue';
import ConnectionHealthPanel from '@/components/common/ConnectionHealthPanel.vue';
import SafetyGuardBanner from '@/components/common/SafetyGuardBanner.vue';
import { useConnectionStore } from '@/stores/connection';
import { useAppStore } from '@/stores/app';
import { useSystemStore } from '@/stores/system';
import { useSettingsStore } from '@/stores/settings';
import { formatDateTime } from '@/utils/format';
import { useHmiRealtime } from '@/composables/useHmiRealtime';
import { useServerStateSync } from '@/composables/useServerStateSync';

const connectionStore = useConnectionStore();
const appStore = useAppStore();
const settingsStore = useSettingsStore();
const systemStore = useSystemStore();

useHmiRealtime();
useServerStateSync();

watch(() => settingsStore.staleThresholdMs, (value) => connectionStore.setStaleAfterMs(value), { immediate: true });
</script>

<style scoped>
.app-layout { display: flex; flex-direction: column; }
.layout-body { display: grid; grid-template-columns: 240px minmax(0, 1fr) 320px; gap: 16px; padding: 16px; min-height: calc(100vh - 112px); }
.main-view { min-width: 0; }
.quick-sidebar { display: flex; flex-direction: column; gap: 16px; }
.footer-bar { display: flex; justify-content: space-between; gap: 12px; padding: 10px 16px; border-top: 1px solid var(--line); color: var(--text-dim); font-size: 12px; flex-wrap: wrap; }
</style>
