<template>
  <section class="panel robot-panel">
    <div class="panel-title">机械臂执行状态</div>
    <div v-if="robotStore.hardware" class="grid-2 content">
      <div class="panel soft-panel">
        <div class="panel-title">关节角</div>
        <div class="data-list inner">
          <div class="data-row" v-for="(joint, index) in robotStore.hardware.joints" :key="index">
            <span class="subtle">J{{ index + 1 }}</span>
            <span>{{ formatJoint(joint) }}</span>
          </div>
        </div>
      </div>
      <div class="panel soft-panel">
        <div class="panel-title">硬件摘要</div>
        <div class="data-list inner">
          <div class="data-row"><span class="subtle">已回零</span><span>{{ formatBool(robotStore.hardware.homed) }}</span></div>
          <div class="data-row"><span class="subtle">夹爪</span><span>{{ robotStore.hardware.gripperOpen ? '打开' : '闭合' }}</span></div>
          <div class="data-row"><span class="subtle">姿态名</span><span>{{ robotStore.hardware.poseName || '--' }}</span></div>
          <div class="data-row"><span class="subtle">执行中</span><span>{{ formatBool(robotStore.hardware.busy) }}</span></div>
          <div class="data-row"><span class="subtle">触发限位</span><span>{{ robotStore.hasJointLimit ? '是' : '否' }}</span></div>
          <div class="data-row"><span class="subtle">最后命令</span><span>{{ robotStore.lastCommand || '--' }}</span></div>
          <div class="data-row"><span class="subtle">命令时间</span><span>{{ formatDateTime(robotStore.lastCommandAt) }}</span></div>
          <div class="data-row"><span class="subtle">错误码</span><span>{{ robotStore.hardware.errorCode || '--' }}</span></div>
        </div>
      </div>
    </div>
    <div v-else class="subtle">硬件状态未加载</div>
  </section>
</template>

<script setup lang="ts">
import { useRobotStore } from '@/stores/robot';
import { formatBool, formatDateTime, formatJoint } from '@/utils/format';

const robotStore = useRobotStore();
</script>

<style scoped>
.robot-panel { padding: 16px; }
.content { margin-top: 12px; }
.soft-panel { background: rgba(255, 255, 255, 0.02); padding: 12px; }
.inner { margin-top: 8px; }
</style>
