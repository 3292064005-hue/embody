<template>
  <section class="vision-page">
    <div class="grid-2">
      <VideoPanel :targets="visionStore.targets" :frame="visionStore.frame" />
      <div class="panel editor-panel">
        <div class="header-row">
          <div>
            <div class="panel-title">标定参数</div>
            <div class="subtle">围绕单相机平面抓取路线，管理 ROI、比例与偏置</div>
          </div>
          <el-tag :type="visionStore.calibration ? 'success' : 'warning'">{{ visionStore.calibration?.profileName || '未加载' }}</el-tag>
        </div>

        <div v-if="localProfile" class="form-grid">
          <el-form label-position="top">
            <el-form-item label="Profile 名称">
              <el-input v-model="localProfile.profileName" />
            </el-form-item>
            <div class="grid-2">
              <el-form-item label="ROI X"><el-input-number v-model="localProfile.roi.x" :min="0" /></el-form-item>
              <el-form-item label="ROI Y"><el-input-number v-model="localProfile.roi.y" :min="0" /></el-form-item>
              <el-form-item label="ROI 宽"><el-input-number v-model="localProfile.roi.width" :min="1" /></el-form-item>
              <el-form-item label="ROI 高"><el-input-number v-model="localProfile.roi.height" :min="1" /></el-form-item>
            </div>
            <el-form-item label="工作台比例 mm/pixel">
              <el-input-number v-model="localProfile.tableScaleMmPerPixel" :min="0.001" :precision="3" :step="0.01" />
            </el-form-item>
            <div class="grid-3">
              <el-form-item label="Offset X"><el-input-number v-model="localProfile.offsets.x" /></el-form-item>
              <el-form-item label="Offset Y"><el-input-number v-model="localProfile.offsets.y" /></el-form-item>
              <el-form-item label="Offset Z"><el-input-number v-model="localProfile.offsets.z" /></el-form-item>
            </div>
            <div class="button-row">
              <el-button type="primary" :loading="visionStore.saving" @click="handleSave">保存标定参数</el-button>
              <el-button @click="reloadProfile">回滚</el-button>
            </div>
          </el-form>
        </div>
      </div>
    </div>

    <div class="grid-2">
      <section class="panel version-panel">
        <div class="panel-title">标定版本</div>
        <el-table :data="visionStore.versions" style="margin-top: 12px" height="300" highlight-current-row @row-click="handleVersionRowClick">
          <el-table-column prop="id" label="版本 ID" width="140" />
          <el-table-column prop="operator" label="操作者" width="120" />
          <el-table-column prop="sampleCount" label="样本数" width="90" />
          <el-table-column prop="meanErrorMm" label="平均误差(mm)" width="130" />
          <el-table-column prop="maxErrorMm" label="最大误差(mm)" width="130" />
          <el-table-column prop="active" label="生效中" width="100">
            <template #default="scope">
              <el-tag :type="scope.row.active ? 'success' : 'info'">{{ scope.row.active ? '是' : '否' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="110">
            <template #default="scope">
              <el-button link type="primary" :disabled="scope.row.active" @click.stop="handleActivate(scope.row.id)">激活</el-button>
            </template>
          </el-table-column>
        </el-table>
      </section>

      <section class="panel compare-panel">
        <div class="panel-title">版本对比</div>
        <div v-if="visionStore.selectedVersion" class="data-list compare-content">
          <div class="data-row"><span class="subtle">版本 ID</span><span>{{ visionStore.selectedVersion.id }}</span></div>
          <div class="data-row"><span class="subtle">操作者</span><span>{{ visionStore.selectedVersion.operator }}</span></div>
          <div class="data-row"><span class="subtle">样本数</span><span>{{ visionStore.selectedVersion.sampleCount ?? '--' }}</span></div>
          <div class="data-row"><span class="subtle">平均误差</span><span>{{ visionStore.selectedVersion.meanErrorMm ?? '--' }} mm</span></div>
          <div class="data-row"><span class="subtle">最大误差</span><span>{{ visionStore.selectedVersion.maxErrorMm ?? '--' }} mm</span></div>
          <div class="data-row"><span class="subtle">更新时间</span><span>{{ formatDateTime(visionStore.selectedVersion.updatedAt) }}</span></div>
        </div>
        <div v-else class="subtle compare-content">请选择一个标定版本查看详情。</div>
      </section>
    </div>

    <TargetTable :targets="visionStore.targets" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import VideoPanel from '@/components/vision/VideoPanel.vue';
import TargetTable from '@/components/vision/TargetTable.vue';
import { useVisionStore } from '@/stores/vision';
import { useCommandBus } from '@/services/commands/commandBus';
import type { CalibrationProfile, CalibrationProfileVersion } from '@/models/vision';
import { formatDateTime } from '@/utils/format';

const visionStore = useVisionStore();
const commandBus = useCommandBus();
const localProfile = ref<CalibrationProfile | null>(null);
const calibration = computed(() => visionStore.calibration);

watch(
  calibration,
  (value) => {
    if (value) localProfile.value = JSON.parse(JSON.stringify(value)) as CalibrationProfile;
  },
  { immediate: true }
);

async function handleSave() {
  if (!localProfile.value) return;
  await commandBus.saveCalibration(localProfile.value);
  ElMessage.success('标定参数已保存');
}

function reloadProfile() {
  if (!visionStore.calibration) return;
  localProfile.value = JSON.parse(JSON.stringify(visionStore.calibration)) as CalibrationProfile;
}

function handleVersionRowClick(row: CalibrationProfileVersion) {
  visionStore.setSelectedVersion(row.id);
}

async function handleActivate(profileId: string) {
  await commandBus.activateCalibrationProfile(profileId);
  ElMessage.success(`已激活标定版本 ${profileId}`);
}
</script>

<style scoped>
.vision-page { display: flex; flex-direction: column; gap: 16px; }
.editor-panel, .version-panel, .compare-panel { padding: 16px; }
.header-row { display: flex; justify-content: space-between; gap: 12px; }
.form-grid { margin-top: 12px; }
.button-row { display: flex; gap: 10px; }
.compare-content { margin-top: 12px; }
</style>
