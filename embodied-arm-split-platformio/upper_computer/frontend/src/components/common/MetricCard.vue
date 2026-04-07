<template>
  <div class="panel metric-card" :class="toneClass">
    <div class="subtle">{{ label }}</div>
    <div class="value">{{ value }}</div>
    <div class="subtle extra">{{ hint }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = withDefaults(
  defineProps<{
    label: string;
    value: string | number;
    hint?: string;
    tone?: 'default' | 'success' | 'warning' | 'danger';
  }>(),
  {
    hint: '--',
    tone: 'default'
  }
);

const toneClass = computed(() => `tone-${props.tone}`);
</script>

<style scoped>
.metric-card {
  padding: 16px;
  border-left-width: 4px;
}

.value {
  margin-top: 12px;
  font-size: 24px;
  font-weight: 800;
}

.extra {
  margin-top: 10px;
}

.tone-default {
  border-left-color: transparent;
}

.tone-success {
  border-left-color: var(--success);
}

.tone-warning {
  border-left-color: var(--warning);
}

.tone-danger {
  border-left-color: var(--danger);
}
</style>
