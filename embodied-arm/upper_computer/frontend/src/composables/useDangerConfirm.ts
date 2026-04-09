import { ElMessageBox } from 'element-plus';
import { useSettingsStore } from '@/stores/settings';

export function useDangerConfirm() {
  const settingsStore = useSettingsStore();

  async function confirmDanger(message: string, title = '危险操作确认'): Promise<boolean> {
    if (!settingsStore.dangerConfirmRequired) {
      return true;
    }
    await ElMessageBox.confirm(message, title, {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning'
    });
    return true;
  }

  return { confirmDanger };
}
