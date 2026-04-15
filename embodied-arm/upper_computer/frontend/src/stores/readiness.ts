import { defineStore } from 'pinia';
import type { ManualCommandLimits, ReadinessState } from '@/models/readiness';
import { RUNTIME_HEALTH_REQUIRED } from '@/generated/runtimeContract';

const defaultManualCommandLimits: ManualCommandLimits = {
  maxServoCartesianDeltaMeters: 0.1,
  maxJogJointStepDeg: 10.0,
};

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
  runtimeDeliveryTrack: 'bootstrap',
  executionBackbone: 'protocol_simulator',
  executionBackboneSummary: {
    runtimeDeliveryTrack: 'bootstrap',
    executionBackbone: 'protocol_simulator',
    executionMode: 'protocol_simulator',
    authoritativeTransport: false,
    sequentialDispatch: false,
    requestedRuntimeProfile: '',
    activeRuntimeLane: '',
    backboneLabel: 'Protocol Simulator',
    firmwareProfile: 'preview_reserved',
    firmwareMessage: 'bootstrap readiness snapshot',
  },
  promotionReceipts: {},
  releaseGates: { repoGate: 'not_executed', targetGate: 'not_executed', hilGate: 'not_executed', releaseChecklistGate: 'not_executed', releaseGate: 'not_executed' },
  firmwareSemanticProfile: 'preview_reserved',
  firmwareSemanticMessage: 'bootstrap readiness snapshot',
  source: 'bootstrap',
  simulated: false,
  authoritative: false,
  manualCommandLimits: { ...defaultManualCommandLimits },
  runtimeConfigVersion: '',
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
      this.runtimeDeliveryTrack = payload.runtimeDeliveryTrack || 'bootstrap';
      this.executionBackbone = payload.executionBackbone || 'protocol_simulator';
      this.executionBackboneSummary = payload.executionBackboneSummary || this.executionBackboneSummary;
      this.promotionReceipts = payload.promotionReceipts || {};
      this.releaseGates = payload.releaseGates || this.releaseGates;
      this.firmwareSemanticProfile = payload.firmwareSemanticProfile || 'preview_reserved';
      this.firmwareSemanticMessage = payload.firmwareSemanticMessage || '';
      this.source = payload.source || 'backend';
      this.simulated = Boolean(payload.simulated);
      this.authoritative = Boolean(payload.authoritative);
      this.manualCommandLimits = payload.manualCommandLimits ? { ...payload.manualCommandLimits } : { ...defaultManualCommandLimits };
      this.runtimeConfigVersion = payload.runtimeConfigVersion || '';
      this.updatedAt = payload.updatedAt;
    }
  }
});
