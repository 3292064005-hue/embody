import { defineStore } from 'pinia';
import type { LogEvent, LogLevel } from '@/models/log';
import { downloadTextFile } from '@/utils/export';

export const useLogStore = defineStore('log', {
  state: (): { records: LogEvent[]; loading: boolean; levelFilter: LogLevel | 'all'; searchText: string; taskIdFilter: string; requestIdFilter: string; correlationIdFilter: string; taskRunIdFilter: string; selectedRecordId: string } => ({
    records: [], loading: false, levelFilter: 'all', searchText: '', taskIdFilter: '', requestIdFilter: '', correlationIdFilter: '', taskRunIdFilter: '', selectedRecordId: ''
  }),
  getters: {
    latestFault(state): LogEvent | null { return state.records.find((item) => item.level === 'fault') || null; },
    faultCount(state): number { return state.records.filter((item) => item.level === 'fault').length; },
    selectedRecord(state): LogEvent | null { return state.records.find((item) => item.id === state.selectedRecordId) || null; },
    filteredRecords(state): LogEvent[] {
      return state.records.filter((item) => {
        const levelMatched = state.levelFilter === 'all' || item.level === state.levelFilter;
        const taskMatched = !state.taskIdFilter || item.taskId?.includes(state.taskIdFilter);
        const requestMatched = !state.requestIdFilter || item.requestId?.includes(state.requestIdFilter);
        const correlationMatched = !state.correlationIdFilter || item.correlationId?.includes(state.correlationIdFilter);
        const taskRunMatched = !state.taskRunIdFilter || item.taskRunId?.includes(state.taskRunIdFilter);
        const searchMatched = !state.searchText || [item.message, item.module, item.event, item.taskId, item.requestId, item.correlationId, item.taskRunId].join(' ').toLowerCase().includes(state.searchText.toLowerCase());
        return levelMatched && taskMatched && requestMatched && correlationMatched && taskRunMatched && searchMatched;
      });
    }
  },
  actions: {
    setRecords(payload: LogEvent[]) { this.records = payload; if (!this.selectedRecordId && payload.length) this.selectedRecordId = payload[0].id; },
    push(record: LogEvent) { this.records = [record, ...this.records].slice(0, 1000); if (!this.selectedRecordId) this.selectedRecordId = record.id; },
    setLevelFilter(level: LogLevel | 'all') { this.levelFilter = level; },
    setSearchText(value: string) { this.searchText = value; },
    setTaskIdFilter(value: string) { this.taskIdFilter = value; },
    setRequestIdFilter(value: string) { this.requestIdFilter = value; },
    setCorrelationIdFilter(value: string) { this.correlationIdFilter = value; },
    setTaskRunIdFilter(value: string) { this.taskRunIdFilter = value; },
    setSelectedRecord(recordId: string) { this.selectedRecordId = recordId; },
    exportFiltered() { downloadTextFile(`logs-${Date.now()}.json`, JSON.stringify(this.filteredRecords, null, 2)); }
  }
});
