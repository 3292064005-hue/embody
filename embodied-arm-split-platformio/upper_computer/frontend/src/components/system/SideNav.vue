<template>
  <nav class="panel side-nav">
    <RouterLink v-for="item in items" :key="item.path" :to="item.path" class="nav-item" :class="{ active: route.path === item.path }">
      <span>{{ item.label }}</span>
      <small>{{ item.desc }}</small>
    </RouterLink>
  </nav>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router';

const route = useRoute();

const items = [
  { path: '/dashboard', label: '总控台', desc: '实时状态与任务控制' },
  { path: '/tasks', label: '任务中心', desc: '模板、队列、历史' },
  { path: '/vision', label: '视觉标定', desc: 'ROI、映射、参数' },
  { path: '/maintenance', label: '手动维护', desc: '点动、回零、测试' },
  { path: '/logs', label: '日志诊断', desc: '事件流、故障、回放' },
  { path: '/settings', label: '系统设置', desc: 'Profile 与安全阈值' }
];
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

.nav-item.active,
.nav-item:hover {
  color: var(--text);
  background: rgba(59, 130, 246, 0.12);
  border-color: rgba(59, 130, 246, 0.28);
}

small {
  font-size: 12px;
}
</style>
