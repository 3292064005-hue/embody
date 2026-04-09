<template>
  <nav class="panel side-nav">
    <component
      :is="item.enabled ? 'RouterLink' : 'div'"
      v-for="item in items"
      :key="item.path"
      :to="item.enabled ? item.path : undefined"
      class="nav-item"
      :class="{ active: route.path === item.path && item.enabled, disabled: !item.enabled }"
    >
      <span class="nav-header">
        <span>{{ item.label }}</span>
        <small v-if="item.badge" class="badge">{{ item.badge }}</small>
      </span>
      <small>{{ item.desc }}</small>
    </component>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { useReadinessStore } from '@/stores/readiness';
import { deriveRuntimeFeatureState } from '@/models/runtimeFeatures';

const route = useRoute();
const readinessStore = useReadinessStore();
const runtimeFeatures = computed(() => deriveRuntimeFeatureState(readinessStore.$state));

const items = computed(() => [
  { path: '/dashboard', label: '总控台', desc: '实时状态与任务控制', enabled: true },
  {
    path: '/tasks',
    label: '任务中心',
    desc: runtimeFeatures.value.taskWorkbenchVisible ? runtimeFeatures.value.runtimeLabel : '需要 authoritative runtime 才开放任务工作台',
    enabled: runtimeFeatures.value.taskWorkbenchVisible,
    badge: runtimeFeatures.value.runtimeBadge,
  },
  { path: '/vision', label: '视觉标定', desc: 'ROI、映射、参数', enabled: true },
  { path: '/maintenance', label: '手动维护', desc: '点动、回零、测试', enabled: true },
  { path: '/logs', label: '日志诊断', desc: '事件流、故障、回放', enabled: true },
  { path: '/settings', label: '系统设置', desc: 'Profile 与安全阈值', enabled: true }
]);
</script>

<style scoped>
.side-nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  position: sticky;
  top: 16px;
  align-self: start;
}

.nav-item {
  padding: 14px 12px;
  border-radius: 12px;
  border: 1px solid transparent;
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--text-dim);
}

.nav-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.badge {
  color: var(--danger);
  font-size: 11px;
  letter-spacing: 0.04em;
}

.nav-item.active,
.nav-item:hover {
  color: var(--text);
  background: rgba(59, 130, 246, 0.12);
  border-color: rgba(59, 130, 246, 0.28);
}

.nav-item.disabled {
  cursor: not-allowed;
  opacity: 0.72;
  background: rgba(148, 163, 184, 0.08);
  border-color: rgba(148, 163, 184, 0.18);
}

.nav-item.disabled:hover {
  color: var(--text-dim);
}

small {
  font-size: 12px;
}
</style>
