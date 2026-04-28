import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest';
import { HmiWebSocket } from '@/services/ws/HmiWebSocket';

type MessageHandler = (event: { data: string }) => void;

class MockSocket {
  static instances: MockSocket[] = [];
  static OPEN = 1;
  static CONNECTING = 0;
  static CLOSED = 3;

  readonly OPEN = MockSocket.OPEN;
  readonly CONNECTING = MockSocket.CONNECTING;
  readonly CLOSED = MockSocket.CLOSED;
  readyState = MockSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: MessageHandler | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];

  constructor(public readonly url: string) {
    MockSocket.instances.push(this);
  }

  send(payload: string): void {
    this.sent.push(payload);
  }

  close(): void {
    this.readyState = MockSocket.CLOSED;
    this.onclose?.();
  }

  open(): void {
    this.readyState = MockSocket.OPEN;
    this.onopen?.();
  }

  emitMessage(payload: Record<string, unknown>): void {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

describe('HmiWebSocket projection dedupe', () => {
  const originalWindow = globalThis.window;
  const originalWebSocket = globalThis.WebSocket;

  beforeEach(() => {
    MockSocket.instances = [];
    const fakeWindow = {
      setInterval,
      clearInterval,
      setTimeout,
      clearTimeout,
    } as unknown as Window & typeof globalThis;
    globalThis.window = fakeWindow;
    globalThis.WebSocket = MockSocket as unknown as typeof WebSocket;
  });

  afterEach(() => {
    globalThis.window = originalWindow;
    globalThis.WebSocket = originalWebSocket;
    vi.restoreAllMocks();
  });

  it('suppresses stale projection frames by topic revision while keeping newer deltas', () => {
    const ws = new HmiWebSocket('ws://unit.test/ws');
    const applied: Array<{ kind: string; value: string }> = [];
    const suppressed: Array<{ topic: string | null; revision: number | null }> = [];

    ws.subscribe<{ mode: string }>('system.state.updated', (payload) => {
      applied.push({ kind: 'system', value: payload.mode });
    });
    ws.subscribe<{ topic: string | null; topicRevision: number | null }>('connection.duplicate_suppressed', (payload) => {
      suppressed.push({ topic: payload.topic, revision: payload.topicRevision });
    });

    ws.connect();
    const socket = MockSocket.instances[0];
    socket.open();

    socket.emitMessage({
      event: 'system.state.updated',
      timestamp: '2026-04-04T20:00:00Z',
      schemaVersion: '1.1',
      deliveryMode: 'snapshot',
      topic: 'system',
      topicRevision: 1,
      data: { mode: 'idle' },
    });
    socket.emitMessage({
      event: 'system.state.updated',
      timestamp: '2026-04-04T20:00:01Z',
      schemaVersion: '1.1',
      deliveryMode: 'delta',
      topic: 'system',
      topicRevision: 1,
      data: { mode: 'duplicate-idle' },
    });
    socket.emitMessage({
      event: 'system.state.updated',
      timestamp: '2026-04-04T20:00:02Z',
      schemaVersion: '1.1',
      deliveryMode: 'delta',
      topic: 'system',
      topicRevision: 2,
      data: { mode: 'manual' },
    });
    socket.emitMessage({
      event: 'audit.event.created',
      timestamp: '2026-04-04T20:00:03Z',
      schemaVersion: '1.1',
      deliveryMode: 'event',
      data: { id: 'audit-1' },
    });

    expect(applied).toEqual([
      { kind: 'system', value: 'idle' },
      { kind: 'system', value: 'manual' },
    ]);
    expect(suppressed).toEqual([{ topic: 'system', revision: 1 }]);
  });
});
