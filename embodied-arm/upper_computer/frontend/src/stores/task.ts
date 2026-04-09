import { defineStore } from 'pinia';
import type { StartTaskPayload, TaskHistoryEntry, TaskProgress, TaskTemplate } from '@/models/task';
import { startTask, stopTask } from '@/services/api/task';
import { useSafetyStore } from '@/stores/safety';
import { useAppStore } from '@/stores/app';
import { useAuditStore } from '@/stores/audit';
import { invalidateResources } from '@/shared/runtime/invalidation';

export const useTaskStore = defineStore('task', {
  state: (): { currentTask: TaskProgress | null; templates: TaskTemplate[]; history: TaskHistoryEntry[]; pending: boolean; selectedTemplateId: string; selectedTargetCategory: string } => ({
    currentTask: null,
    templates: [],
    history: [],
    pending: false,
    selectedTemplateId: '',
    selectedTargetCategory: 'red'
  }),
  getters: {
    currentTemplate(state): TaskTemplate | undefined {
      return state.templates.find((item) => item.id === state.selectedTemplateId);
    },
    successRate(state): number {
      if (!state.history.length) return 0;
      const success = state.history.filter((item) => item.success).length;
      return Math.round((success / state.history.length) * 100);
    }
  },
  actions: {
    setCurrentTask(payload: TaskProgress | null) { this.currentTask = payload; },
    setTemplates(payload: TaskTemplate[]) {
      this.templates = payload;
      if (!this.selectedTemplateId && payload.length) {
        this.selectedTemplateId = payload[0].id;
        this.selectedTargetCategory = payload[0].defaultTargetCategory || this.selectedTargetCategory;
      }
    },
    setHistory(payload: TaskHistoryEntry[]) { this.history = payload; },
    setSelectedTemplate(templateId: string) {
      this.selectedTemplateId = templateId;
      const template = this.templates.find((item) => item.id === templateId);
      if (template?.defaultTargetCategory) this.selectedTargetCategory = template.defaultTargetCategory;
    },
    setSelectedTargetCategory(targetCategory: string) { this.selectedTargetCategory = targetCategory; },
    async startTask(payload: StartTaskPayload) {
      if (this.pending) return;
      const safetyStore = useSafetyStore();
      const appStore = useAppStore();
      const auditStore = useAuditStore();
      if (!safetyStore.canStartTask.allowed) {
        auditStore.recordBlocked('task.start', appStore.operatorRole, safetyStore.canStartTask.reason, payload as unknown as Record<string, unknown>, safetyStore.guardSummary);
        throw new Error(safetyStore.canStartTask.reason);
      }
      this.pending = true;
      const audit = auditStore.createEntry({ action: 'task.start', actorRole: appStore.operatorRole, reason: '命令已受理，等待网关回执', payload: payload as unknown as Record<string, unknown>, guardSummary: safetyStore.guardSummary });
      try {
        const decision = await startTask(payload);
        auditStore.updateStatus(audit.id, 'success', `启动任务命令发送成功（taskId=${decision.taskId}，run=${decision.taskRunId}）`);
        invalidateResources(['task.current', 'task.history', 'system', 'logs', 'hardware']);
      } catch (error) {
        auditStore.updateStatus(audit.id, 'failed', error instanceof Error ? error.message : '启动任务失败');
        throw error;
      } finally {
        this.pending = false;
      }
    },
    async stopTask() {
      if (this.pending) return;
      const safetyStore = useSafetyStore();
      const appStore = useAppStore();
      const auditStore = useAuditStore();
      if (!safetyStore.canStopTask.allowed) {
        auditStore.recordBlocked('task.stop', appStore.operatorRole, safetyStore.canStopTask.reason, undefined, safetyStore.guardSummary);
        throw new Error(safetyStore.canStopTask.reason);
      }
      this.pending = true;
      const audit = auditStore.createEntry({ action: 'task.stop', actorRole: appStore.operatorRole, reason: '停止任务命令已受理', guardSummary: safetyStore.guardSummary });
      try {
        await stopTask();
        auditStore.updateStatus(audit.id, 'success', '停止任务命令发送成功');
        invalidateResources(['task.current', 'task.history', 'system', 'logs', 'hardware']);
      } catch (error) {
        auditStore.updateStatus(audit.id, 'failed', error instanceof Error ? error.message : '停止任务失败');
        throw error;
      } finally {
        this.pending = false;
      }
    }
  }
});
