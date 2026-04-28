import { defineStore } from 'pinia';
import type { OperatorRole } from '@/models/safety';
import { APP_TITLE } from '@/constants/system';
import { readLocalStorage, writeLocalStorage } from '@/utils/storage';

const APP_ROLE_KEY = 'embodied-arm-hmi:operator-role';
const LEGACY_APP_ROLE_KEY = 'embodied-arm-hmi:operator-mode';

function readOperatorRolePreference(): OperatorRole {
  const role = readLocalStorage<OperatorRole>(APP_ROLE_KEY, readLocalStorage<OperatorRole>(LEGACY_APP_ROLE_KEY, 'operator'));
  return role === 'viewer' || role === 'operator' || role === 'maintainer' ? role : 'operator';
}

function persistOperatorRolePreference(role: OperatorRole): void {
  writeLocalStorage(APP_ROLE_KEY, role);
  writeLocalStorage(LEGACY_APP_ROLE_KEY, role);
}

export const useAppStore = defineStore('app', {
  state: () => ({
    appTitle: APP_TITLE,
    operatorRole: readOperatorRolePreference(),
    commandDialogOpen: false,
    compactSidebar: false
  }),
  actions: {
    setOperatorRole(role: OperatorRole) {
      this.operatorRole = role;
      persistOperatorRolePreference(role);
    },
    setCompactSidebar(compact: boolean) {
      this.compactSidebar = compact;
    }
  }
});
