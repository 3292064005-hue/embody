import { defineStore } from 'pinia';
import { readLocalStorage, writeLocalStorage } from '@/utils/storage';

const SETTINGS_KEY = 'embodied-arm-hmi:settings';

type SettingsState = {
  profileName: string;
  mockEnabled: boolean;
  autoRefresh: boolean;
  dangerConfirmRequired: boolean;
  staleThresholdMs: number;
  autoReconnect: boolean;
  maxTimelineRecords: number;
  readonlyOnSyncFailure: boolean;
};

const defaultState: SettingsState = {
  profileName: 'default_bench_topview',
  mockEnabled: import.meta.env.VITE_ENABLE_MOCK === 'true',
  autoRefresh: true,
  dangerConfirmRequired: true,
  staleThresholdMs: 8000,
  autoReconnect: true,
  maxTimelineRecords: 500,
  readonlyOnSyncFailure: true
};

export const useSettingsStore = defineStore('settings', {
  state: (): SettingsState => readLocalStorage<SettingsState>(SETTINGS_KEY, defaultState),
  actions: {
    patch(payload: Partial<SettingsState>) {
      Object.assign(this, payload);
      writeLocalStorage(SETTINGS_KEY, {
        profileName: this.profileName,
        mockEnabled: this.mockEnabled,
        autoRefresh: this.autoRefresh,
        dangerConfirmRequired: this.dangerConfirmRequired,
        staleThresholdMs: this.staleThresholdMs,
        autoReconnect: this.autoReconnect,
        maxTimelineRecords: this.maxTimelineRecords,
        readonlyOnSyncFailure: this.readonlyOnSyncFailure
      });
    }
  }
});
