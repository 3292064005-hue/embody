<template>
  <section class="panel safety-banner" :class="toneClass">
    <div class="banner-head">
      <div>
        <div class="panel-title">控制安全状态</div>
        <div class="subtle">基于连接状态、系统模式、回零状态、权限模式、故障状态与只读降级联合判定</div>
      </div>
      <el-tag :type="bannerTag">{{ bannerLabel }}</el-tag>
    </div>
    <div class="banner-body subtle">{{ bannerReason }}</div>
    <div class="banner-foot subtle">{{ safetyStore.guardSummary }}</div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useSafetyStore } from '@/stores/safety';

const safetyStore = useSafetyStore();
const bannerReason = computed(() => !safetyStore.canStartTask.allowed ? safetyStore.canStartTask.reason : !safetyStore.canJog.allowed ? safetyStore.canJog.reason : '系统满足任务发起条件；维护动作仍会单独校验。');
const bannerLabel = computed(() => !safetyStore.canStartTask.allowed ? '受限' : !safetyStore.canJog.allowed ? '部分受限' : '正常');
const bannerTag = computed(() => !safetyStore.canStartTask.allowed ? 'danger' : !safetyStore.canJog.allowed ? 'warning' : 'success');
const toneClass = computed(() => `tone-${bannerTag.value}`);
</script>

<style scoped>
.safety-banner { padding: 16px; }
.banner-head { display: flex; justify-content: space-between; gap: 12px; }
.banner-body { margin-top: 10px; }
.banner-foot { margin-top: 8px; font-size: 12px; }
.tone-danger { border-color: rgba(239, 68, 68, 0.35); }
.tone-warning { border-color: rgba(245, 158, 11, 0.35); }
.tone-success { border-color: rgba(34, 197, 94, 0.35); }
</style>
