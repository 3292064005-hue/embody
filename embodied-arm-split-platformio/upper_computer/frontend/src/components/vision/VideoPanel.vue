<template>
  <section class="panel video-panel">
    <div class="panel-head">
      <div>
        <div class="panel-title">实时视觉画面</div>
        <div class="subtle">固定工位 / 单相机 / 平面抓取</div>
      </div>
      <el-tag :type="targets.length ? 'success' : 'warning'">{{ targets.length }} 个目标</el-tag>
    </div>
    <div class="video-stage">
      <div class="frame-label">CAM STREAM</div>
      <div v-for="target in targets" :key="target.id" class="overlay target" :style="overlayStyle(target.pixelX, target.pixelY)">
        <div>{{ target.category }}</div>
        <small>{{ Math.round(target.confidence * 100) }}%</small>
      </div>
    </div>
    <div class="legend subtle">
      当前为前端占位渲染层，接入真实视频流时替换为 MJPEG / WebRTC / 帧图接口；保留目标框、抓取点与 ROI 叠加层不变。
    </div>
  </section>
</template>

<script setup lang="ts">
import type { VisionTarget } from '@/models/vision';

defineProps<{
  targets: VisionTarget[];
}>();

function overlayStyle(x: number, y: number) {
  return {
    left: `${Math.max(8, Math.min(88, x / 6.4))}%`,
    top: `${Math.max(8, Math.min(88, y / 4.8))}%`
  };
}
</script>

<style scoped>
.video-panel {
  padding: 16px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.video-stage {
  position: relative;
  height: 420px;
  border-radius: 14px;
  border: 1px dashed rgba(142, 160, 186, 0.25);
  background:
    linear-gradient(0deg, rgba(5, 10, 18, 0.45), rgba(5, 10, 18, 0.45)),
    radial-gradient(circle at center, rgba(59, 130, 246, 0.10), transparent 42%),
    linear-gradient(135deg, #0f172a, #111827 48%, #0f172a);
  overflow: hidden;
}

.frame-label {
  position: absolute;
  top: 12px;
  left: 12px;
  font-size: 12px;
  color: var(--text-dim);
}

.overlay {
  position: absolute;
  transform: translate(-50%, -50%);
  border: 1px solid rgba(34, 197, 94, 0.7);
  background: rgba(34, 197, 94, 0.15);
  color: white;
  border-radius: 8px;
  padding: 4px 8px;
  font-size: 12px;
  min-width: 72px;
  text-align: center;
}

.overlay small {
  display: block;
  margin-top: 2px;
  color: rgba(255,255,255,0.8);
}

.legend {
  margin-top: 10px;
}
</style>
