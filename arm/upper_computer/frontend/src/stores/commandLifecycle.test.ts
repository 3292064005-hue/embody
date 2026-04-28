import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

import { useCommandLifecycleStore } from '@/stores/commandLifecycle';


describe('command lifecycle store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('keeps accepted commands pending until task state confirms success', () => {
    const store = useCommandLifecycleStore();
    store.registerAccepted('task.start', {
      accepted: true,
      success: false,
      requestId: 'req-task-start',
      operationId: 'op-task-start',
      receiptId: 'receipt-task-start',
      authoritativeStatus: 'accepted',
      completionPending: true,
      localPreviewOnly: false,
      message: 'task start accepted',
    }, {
      message: '任务启动命令已受理',
      expectation: { taskId: 'task-1', taskRunId: 'run-1' },
    });

    expect(store.pendingCount).toBe(1);
    expect(store.records[0].status).toBe('accepted');

    store.reconcileTask({
      taskId: 'task-1',
      taskType: 'pick_place',
      status: 'running',
      stage: 'planning',
      runtimePhase: 'planning',
      startedAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    } as never);

    expect(store.pendingCount).toBe(0);
    expect(store.records[0].status).toBe('success');
    expect(store.records[0].completionPending).toBe(false);
    expect(store.records[0].message).toContain('任务已进入权威运行态');
  });

  it('marks preview-only accepted commands as observed immediately', () => {
    const store = useCommandLifecycleStore();
    store.registerAccepted('system.home', {
      accepted: true,
      success: false,
      requestId: 'req-preview-home',
      authoritativeStatus: 'observed',
      completionPending: true,
      localPreviewOnly: true,
      message: 'preview only',
    }, {
      message: '回零命令已受理',
    });

    expect(store.pendingCount).toBe(0);
    expect(store.records[0].status).toBe('observed');
    expect(store.records[0].finalizedAt).toBeTruthy();
  });

  it('finalizes accepted commands from terminal receipts', () => {
    const store = useCommandLifecycleStore();
    store.registerAccepted('hardware.gripper', {
      accepted: true,
      success: false,
      requestId: 'req-gripper',
      authoritativeStatus: 'accepted',
      completionPending: true,
      localPreviewOnly: false,
      message: 'accepted',
    }, {
      message: '夹爪命令已受理',
      expectation: { gripperOpen: true },
    });

    store.mergeReceipt({
      requestId: 'req-gripper',
      status: 'failed',
      message: 'hardware jammed',
      id: 'receipt-gripper',
    });

    expect(store.pendingCount).toBe(0);
    expect(store.records[0].status).toBe('failed');
    expect(store.records[0].receiptId).toBe('receipt-gripper');
    expect(store.records[0].message).toBe('hardware jammed');
  });

  it('downgrades stale pending commands to observed after timeout', () => {
    const store = useCommandLifecycleStore();
    store.registerAccepted('system.recover', {
      accepted: true,
      success: false,
      requestId: 'req-recover',
      authoritativeStatus: 'accepted',
      completionPending: true,
      localPreviewOnly: false,
      message: 'accepted',
    }, {
      message: '恢复命令已受理',
    });

    const acceptedAt = Date.parse(store.records[0].acceptedAt);
    store.sweepTimeouts(acceptedAt + 20_000);

    expect(store.pendingCount).toBe(0);
    expect(store.records[0].status).toBe('observed');
    expect(store.records[0].message).toContain('未收到终态回执');
  });
});
