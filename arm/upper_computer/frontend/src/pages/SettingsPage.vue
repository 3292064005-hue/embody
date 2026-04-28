<template>
  <section class="settings-page">
    <div class="panel page-panel">
      <div class="panel-title">本地偏好</div>
      <div class="grid-2 form-grid">
        <div class="panel inner-panel">
          <div class="panel-title">HMI 本地偏好</div>
          <el-form label-position="top" style="margin-top: 12px">
            <el-form-item label="默认标定 Profile 名称（仅本地记忆）">
              <el-input :model-value="settingsStore.profileName" @input="settingsStore.patch({ profileName: String($event) })" />
            </el-form-item>
            <el-form-item label="Mock 能力（由环境变量控制）">
              <el-switch :model-value="settingsStore.mockEnabled" disabled />
            </el-form-item>
            <el-form-item label="自动刷新（仅当前 HMI）">
              <el-switch :model-value="settingsStore.autoRefresh" @change="handleAutoRefreshChange" />
            </el-form-item>
            <el-form-item label="危险操作二次确认（仅当前 HMI）">
              <el-switch :model-value="settingsStore.dangerConfirmRequired" @change="handleDangerConfirmChange" />
            </el-form-item>
            <el-form-item label="同步失败后只读降级（仅当前 HMI）">
              <el-switch :model-value="settingsStore.readonlyOnSyncFailure" @change="handleReadonlyDegradedChange" />
            </el-form-item>
            <el-form-item label="实时链路过期阈值 ms（仅影响当前 HMI）">
              <el-input-number :model-value="settingsStore.staleThresholdMs" :min="1000" :step="1000" @change="handleStaleThresholdChange" />
            </el-form-item>
            <el-form-item label="时间线保留上限（仅本地显示）">
              <el-input-number :model-value="settingsStore.maxTimelineRecords" :min="100" :step="100" @change="handleTimelineLimitChange" />
            </el-form-item>
          </el-form>
        </div>
        <div class="panel inner-panel">
          <div class="panel-title">作用边界说明</div>
          <ul class="bullet-list subtle">
            <li>本页所有开关与阈值都只写入浏览器本地存储，不直接修改后端 runtime authority。</li>
            <li>系统权威配置仍以后端网关、ROS2 与 runtime authority 为准；前端不会绕过它们改写执行面。</li>
            <li>默认标定 Profile 名称只影响当前 HMI 的表单默认值与显示习惯，不会自动激活后端标定版本。</li>
            <li>危险命令仍必须经过 Gateway 门禁、审计链与回执链；本页不会放宽这些限制。</li>
            <li>Mock 能力仍由环境变量控制；本页只展示当前是否启用，不提供绕过入口。</li>
            <li>若未来需要真正的系统配置页，应单独落后端 authority/config contract，而不是复用本地偏好页。</li>
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
