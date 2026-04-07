<template>
  <section class="panel table-panel">
    <div class="panel-head">
      <div class="panel-title">目标列表</div>
      <div class="subtle">按工作台坐标与可抓取性快速检查识别结果</div>
    </div>
    <el-table :data="targets" style="width: 100%; margin-top: 12px" height="260">
      <el-table-column prop="id" label="ID" width="120" />
      <el-table-column prop="category" label="类别" width="100" />
      <el-table-column label="工作台坐标">
        <template #default="scope">
          ({{ scope.row.worldX.toFixed(1) }}, {{ scope.row.worldY.toFixed(1) }})
        </template>
      </el-table-column>
      <el-table-column prop="confidence" label="置信度" width="110">
        <template #default="scope">
          {{ (scope.row.confidence * 100).toFixed(1) }}%
        </template>
      </el-table-column>
      <el-table-column prop="angle" label="角度" width="100">
        <template #default="scope">
          {{ scope.row.angle?.toFixed(1) ?? '--' }}
        </template>
      </el-table-column>
      <el-table-column prop="graspable" label="可抓取" width="100">
        <template #default="scope">
          <el-tag :type="scope.row.graspable ? 'success' : 'danger'">{{ scope.row.graspable ? '是' : '否' }}</el-tag>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<script setup lang="ts">
import type { VisionTarget } from '@/models/vision';

defineProps<{ targets: VisionTarget[] }>();
</script>

<style scoped>
.table-panel {
  padding: 16px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
</style>
