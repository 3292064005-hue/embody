import { defineStore } from 'pinia';
import type { CalibrationProfile, CalibrationProfileVersion, VisionTarget } from '@/models/vision';
import { activateCalibrationProfile, saveCalibrationProfile } from '@/services/api/vision';
import { invalidateResources } from '@/shared/runtime/invalidation';

export const useVisionStore = defineStore('vision', {
  state: (): { targets: VisionTarget[]; calibration: CalibrationProfile | null; versions: CalibrationProfileVersion[]; loading: boolean; saving: boolean; selectedVersionId: string } => ({
    targets: [], calibration: null, versions: [], loading: false, saving: false, selectedVersionId: ''
  }),
  getters: {
    graspableTargets(state): VisionTarget[] { return state.targets.filter((target) => target.graspable); },
    averageConfidence(state): number {
      if (!state.targets.length) return 0;
      return state.targets.reduce((sum, target) => sum + target.confidence, 0) / state.targets.length;
    },
    selectedVersion(state): CalibrationProfileVersion | undefined { return state.versions.find((item) => item.id === state.selectedVersionId) || state.versions[0]; }
  },
  actions: {
    setTargets(payload: VisionTarget[]) { this.targets = payload; },
    setCalibration(payload: CalibrationProfile | null) { this.calibration = payload; },
    setVersions(payload: CalibrationProfileVersion[]) {
      this.versions = payload;
      if (!this.selectedVersionId && payload.length) this.selectedVersionId = payload[0].id;
    },
    setSelectedVersion(versionId: string) { this.selectedVersionId = versionId; },
    async saveCalibration(profile: CalibrationProfile) {
      this.saving = true;
      try {
        await saveCalibrationProfile(profile);
        this.calibration = profile;
        invalidateResources(['vision.calibration', 'vision.versions', 'logs']);
      } finally {
        this.saving = false;
      }
    },
    async activateProfile(profileId: string) {
      await activateCalibrationProfile(profileId);
      invalidateResources(['vision.calibration', 'vision.versions', 'logs']);
    }
  }
});
