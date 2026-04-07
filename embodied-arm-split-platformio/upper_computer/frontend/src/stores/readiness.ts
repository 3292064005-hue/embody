import { defineStore } from 'pinia';
import type { ReadinessState } from '@/models/readiness';
import { RUNTIME_HEALTH_REQUIRED } from '@/generated/runtimeContract';

const emptyReadiness: ReadinessState = {
  mode: 'boot',
  controllerMode: 'idle',
  runtimePhase: 'boot',
  taskStage: 'created',
  runtimeHealthy: false,
  modeReady: false,
  allReady: false,
  requiredChecks: ['ros2'],
  runtimeRequiredChecks: [...RUNTIME_HEALTH_REQUIRED],
  missingChecks: ['ros2'],
  runtimeMissingChecks: [...RUNTIME_HEALTH_REQUIRED],
  missingDetails: [{ name: 'ros2', detail: 'not_connected' }],
  checks: {},
  commandPolicies: {},
  commandSummary: { allowed: [], blocked: [], readyCount: 0, blockedCount: 0 },
  source: 'bootstrap',
  simulated: false,
  authoritative: false,
  updatedAt: ''
};

export const useReadinessStore = defineStore('readiness', {
  state: (): ReadinessState => ({ ...emptyReadiness }),
  getters: {
    failingChecks(state): Array<{ name: string; detail: string }> {
      if (state.missingDetails?.length) {
        return state.missingDetails.map((item) => ({ name: item.name, detail: item.detail }));
      }
      return Object.entries(state.checks)
        .filter(([, value]) => !(value.effectiveOk ?? value.ok))
        .map(([name, value]) => ({ name, detail: value.detail }));
    }
  },
  actions: {
    setReadiness(payload: ReadinessState) {
      this.mode = payload.mode;
      this.controllerMode = payload.controllerMode || 'idle';
      this.runtimePhase = payload.runtimePhase || 'boot';
      this.taskStage = payload.taskStage || 'created';
      this.runtimeHealthy = Boolean(payload.runtimeHealthy);
      this.modeReady = Boolean(payload.modeReady ?? payload.allReady);
      this.allReady = Boolean(payload.allReady);
      this.requiredChecks = payload.requiredChecks || [];
      this.runtimeRequiredChecks = payload.runtimeRequiredChecks || [];
      this.missingChecks = payload.missingChecks || [];
      this.runtimeMissingChecks = payload.runtimeMissingChecks || [];
      this.missingDetails = payload.missingDetails || [];
      this.checks = payload.checks;
      this.commandPolicies = payload.commandPolicies || {};
      this.commandSummary = payload.commandSummary || { allowed: [], blocked: [], readyCount: 0, blockedCount: 0 };
      this.source = payload.source || 'backend';
      this.simulated = Boolean(payload.simulated);
      this.authoritative = Boolean(payload.authoritative);
      this.updatedAt = payload.updatedAt;
    }
  }
});
