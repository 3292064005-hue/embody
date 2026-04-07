<template>
  <section class="settings-page">
    <div class="panel page-panel">
      <div class="panel-title">系统设置</div>
      <div class="grid-2 form-grid">
        <div class="panel inner-panel">
          <div class="panel-title">运行配置</div>
          <el-form label-position="top" style="margin-top: 12px">
            <el-form-item label="Profile 名称">
              <el-input :model-value="settingsStore.profileName" @input="settingsStore.patch({ profileName: String($event) })" />
            </el-form-item>
            <el-form-item label="Mock 模式">
              <el-switch :model-value="settingsStore.mockEnabled" disabled />
            </el-form-item>
            <el-form-item label="自动刷新">
              <el-switch :model-value="settingsStore.autoRefresh" @change="handleAutoRefreshChange" />
            </el-form-item>
            <el-form-item label="危险操作二次确认">
              <el-switch :model-value="settingsStore.dangerConfirmRequired" @change="handleDangerConfirmChange" />
            </el-form-item>
            <el-form-item label="同步失败后只读降级">
              <el-switch :model-value="settingsStore.readonlyOnSyncFailure" @change="handleReadonlyDegradedChange" />
            </el-form-item>
            <el-form-item label="实时链路过期阈值(ms)">
              <el-input-number :model-value="settingsStore.staleThresholdMs" :min="1000" :step="1000" @change="handleStaleThresholdChange" />
            </el-form-item>
            <el-form-item label="时间线保留上限">
              <el-input-number :model-value="settingsStore.maxTimelineRecords" :min="100" :step="100" @change="handleTimelineLimitChange" />
            </el-form-item>
          </el-form>
        </div>
        <div class="panel inner-panel">
          <div class="panel-title">冻结说明</div>
          <ul class="bullet-list subtle">
            <li>V1/V2 阶段固定为本地主控 HMI，不做远程公网控制。</li>
            <li>核心控制以后端网关和 ROS2 为准，前端不直接驱动底层执行器。</li>
            <li>权限模型已冻结为 viewer / operator / maintainer，并与 Gateway 审计和危险命令门禁对齐。</li>
            <li>危险命令必须显式提示、通过门禁并进入审计链。</li>
            <li>Mock 能力由环境变量控制，便于前后端解耦开发与演示。</li>
            <li>日志、标定、任务历史必须可追溯，避免“能复现但无法解释”的风险。</li>
          </ul>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { useSettingsStore } from '@/stores/settings';

const settingsStore = useSettingsStore();

function handleAutoRefreshChange(value: boolean | string | number) {
  settingsStore.patch({ autoRefresh: Boolean(value) });
}

function handleDangerConfirmChange(value: boolean | string | number) {
  settingsStore.patch({ dangerConfirmRequired: Boolean(value) });
}

function handleReadonlyDegradedChange(value: boolean | string | number) {
  settingsStore.patch({ readonlyOnSyncFailure: Boolean(value) });
}

function handleStaleThresholdChange(value: number | null | undefined) {
  settingsStore.patch({ staleThresholdMs: Number(value || 8000) });
}

function handleTimelineLimitChange(value: number | null | undefined) {
  settingsStore.patch({ maxTimelineRecords: Number(value || 500) });
}
</script>

<style scoped>
.settings-page { display: flex; flex-direction: column; gap: 16px; }
.page-panel { padding: 18px; }
.form-grid { margin-top: 16px; }
.inner-panel { padding: 16px; }
.bullet-list { margin: 12px 0 0; line-height: 1.8; padding-left: 18px; }
</style>
