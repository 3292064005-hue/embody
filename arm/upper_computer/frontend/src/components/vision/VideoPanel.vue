<template>
  <section class="panel video-panel">
    <div class="panel-head">
      <div>
        <div class="panel-title">视觉帧 / 目标态势</div>
        <div class="subtle">统一承载 frame snapshot 与目标叠加，不再把 overlay 与底图拆成两套面板语义。</div>
      </div>
      <div class="head-tags">
        <el-tag :type="frameStatusType">{{ frameStatusLabel }}</el-tag>
        <el-tag :type="providerTagType">{{ providerTagLabel }}</el-tag>
        <el-tag :type="targets.length ? 'success' : 'warning'">{{ targets.length }} 个目标</el-tag>
      </div>
    </div>
    <div class="video-stage">
      <img v-if="frame.available && frame.previewDataUrl" class="frame-preview" :src="frame.previewDataUrl" alt="vision-frame" />
      <div v-else class="frame-fallback subtle">
        {{ frame.message || 'frame stream unavailable' }}
      </div>
      <div class="frame-label">{{ frameLabel }}</div>
      <div v-for="target in targets" :key="target.id" class="overlay target" :style="overlayStyle(target.pixelX, target.pixelY)">
        <div>{{ target.category }}</div>
        <small>{{ Math.round(target.confidence * 100) }}%</small>
      </div>
    </div>
    <div class="legend subtle">
      <span>provider={{ frame.providerKind || 'unknown' }}</span>
      <span> · ingressLive={{ Boolean(frame.frameIngressLive) }}</span>
      <span> · cameraLive={{ Boolean(frame.cameraLive) }}</span>
      <span> · synthetic={{ Boolean(frame.syntheticPreview) }}</span>
      <span> · targetCount={{ frame.targetCount }}</span>
      <span v-if="frame.authoritativeVisualSource"> · targetSource={{ frame.authoritativeVisualSource }}</span>
      <span v-if="frame.mockProfile"> · profile={{ frame.mockProfile }}</span>
      <span v-if="frame.frameSequence"> · seq={{ frame.frameSequence }}</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { VisionFrame, VisionTarget } from '@/models/vision';

const props = defineProps<{
  targets: VisionTarget[];
  frame: VisionFrame;
}>();

const frameStatusLabel = computed(() => {
  if (!props.frame.available && props.frame.frameIngressLive) return 'METADATA LIVE';
  if (!props.frame.available) return 'FRAME DEGRADED';
  if (props.frame.cameraLive) return 'CAMERA LIVE';
  if (props.frame.frameIngressLive && props.frame.syntheticPreview) return 'SYNTHETIC LIVE';
  if (props.frame.frameIngressLive) return 'FRAME LIVE';
  return 'SNAPSHOT ONLY';
});

const frameStatusType = computed(() => {
  if (!props.frame.available && props.frame.frameIngressLive) return 'info';
  if (!props.frame.available) return 'warning';
  return props.frame.cameraLive || props.frame.frameIngressLive ? 'success' : 'info';
});

const providerTagLabel = computed(() => {
  if (props.frame.providerKind === 'live_frame_summary') return 'LIVE SUMMARY';
  if (props.frame.providerKind) return String(props.frame.providerKind).toUpperCase();
  if (props.frame.sourceType) return String(props.frame.sourceType).toUpperCase();
  return 'UNKNOWN';
});

const providerTagType = computed(() => props.frame.cameraLive ? 'success' : props.frame.syntheticPreview ? 'info' : 'warning');

const frameLabel = computed(() => {
  if (!props.frame.available) return 'FRAME OFFLINE';
  return props.frame.providerLabel || props.frame.providerKind || props.frame.sourceType || 'FRAME SNAPSHOT';
});

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

.head-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.video-stage {
  position: relative;
  height: 420px;
  border-radius: 14px;
  border: 1px solid rgba(142, 160, 186, 0.25);
  background: #0f172a;
  overflow: hidden;
}

.frame-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.frame-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 24px;
}

.frame-label {
  position: absolute;
  top: 12px;
  left: 12px;
  font-size: 12px;
  color: var(--text-dim);
  background: rgba(15, 23, 42, 0.7);
  border-radius: 999px;
  padding: 4px 8px;
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
