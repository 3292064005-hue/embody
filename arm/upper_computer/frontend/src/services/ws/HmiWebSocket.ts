import type { WsEvent } from '@/models/api';

type Listener<T = unknown> = (payload: T) => void;
type HmiWebSocketOptions = { heartbeatIntervalMs?: number; maxReconnectDelayMs?: number };

function isWsEnvelope(payload: unknown): payload is WsEvent<unknown> {
  return typeof payload === 'object' && payload !== null && 'event' in payload && 'timestamp' in payload && 'data' in payload;
}

export class HmiWebSocket {
  private socket: WebSocket | null = null;
  private listeners = new Map<string, Set<Listener>>();
  private reconnectTimer: number | null = null;
  private heartbeatTimer: number | null = null;
  private manualClose = false;
  private reconnectAttempts = 0;
  private latestProjectionRevision = new Map<string, number>();
  constructor(private readonly url: string, options?: HmiWebSocketOptions) {
    this.heartbeatIntervalMs = options?.heartbeatIntervalMs ?? 10000;
    this.maxReconnectDelayMs = options?.maxReconnectDelayMs ?? 15000;
  }
  private readonly heartbeatIntervalMs: number;
  private readonly maxReconnectDelayMs: number;

  connect(): void {
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) return;
    this.manualClose = false;
    this.resetProjectionRevisions();
    this.emit('connection.state', { wsState: 'connecting', timestamp: new Date().toISOString() });
    this.socket = new WebSocket(this.url);
    this.socket.onopen = () => { this.reconnectAttempts = 0; this.startHeartbeat(); this.emit('connection.open', { connected: true, timestamp: new Date().toISOString() }); this.emit('connection.state', { wsState: 'open', timestamp: new Date().toISOString() }); };
    this.socket.onmessage = (event) => {
      const receivedAt = Date.now();
      try {
        const parsed = JSON.parse(String(event.data)) as unknown;
        if (!isWsEnvelope(parsed)) { this.emit('connection.parse_error', { raw: event.data, timestamp: new Date().toISOString() }); return; }
        const sourceTimestamp = new Date(parsed.timestamp).getTime();
        const latencyMs = Number.isFinite(sourceTimestamp) ? Math.max(0, receivedAt - sourceTimestamp) : null;
        this.emit('connection.message', {
          eventName: parsed.event,
          timestamp: parsed.timestamp,
          latencyMs,
          deliveryMode: parsed.deliveryMode ?? 'event',
          topic: parsed.topic ?? null,
          topicRevision: typeof parsed.topicRevision === 'number' ? parsed.topicRevision : null,
        });
        if (parsed.event === 'server.pong') this.emit('connection.pong', { timestamp: parsed.timestamp, latencyMs });
        if (this.shouldSuppressProjectionEnvelope(parsed)) {
          this.emit('connection.duplicate_suppressed', {
            eventName: parsed.event,
            timestamp: parsed.timestamp,
            deliveryMode: parsed.deliveryMode ?? 'event',
            topic: parsed.topic ?? null,
            topicRevision: typeof parsed.topicRevision === 'number' ? parsed.topicRevision : null,
          });
          return;
        }
        this.emit(parsed.event, parsed.data);
      } catch {
        this.emit('connection.parse_error', { raw: event.data, timestamp: new Date().toISOString() });
      }
    };
    this.socket.onclose = () => { this.stopHeartbeat(); this.emit('connection.close', { connected: false, timestamp: new Date().toISOString() }); this.emit('connection.state', { wsState: 'closed', timestamp: new Date().toISOString() }); if (!this.manualClose) this.scheduleReconnect(); };
    this.socket.onerror = () => { this.emit('connection.error', { connected: false, timestamp: new Date().toISOString() }); this.emit('connection.state', { wsState: 'error', timestamp: new Date().toISOString() }); };
  }

  disconnect(): void {
    this.manualClose = true;
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer);
    this.stopHeartbeat();
    this.resetProjectionRevisions();
    this.emit('connection.state', { wsState: 'closing', timestamp: new Date().toISOString() });
    this.socket?.close();
    this.socket = null;
  }

  subscribe<T = unknown>(eventName: string, listener: Listener<T>): () => void {
    if (!this.listeners.has(eventName)) this.listeners.set(eventName, new Set());
    this.listeners.get(eventName)?.add(listener as Listener);
    return () => this.listeners.get(eventName)?.delete(listener as Listener);
  }

  send(event: string, data: Record<string, unknown> = {}): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) return;
    const payload: WsEvent<Record<string, unknown>> = { event, timestamp: new Date().toISOString(), source: 'embodied-arm-hmi', schemaVersion: '1.0', data };
    this.socket.send(JSON.stringify(payload));
  }

  private emit(eventName: string, payload: unknown): void { this.listeners.get(eventName)?.forEach((listener) => listener(payload)); }

  private resetProjectionRevisions(): void {
    this.latestProjectionRevision.clear();
  }

  private shouldSuppressProjectionEnvelope(payload: WsEvent<unknown>): boolean {
    const deliveryMode = payload.deliveryMode ?? 'event';
    if (deliveryMode !== 'snapshot' && deliveryMode !== 'delta') return false;
    if (!payload.topic || typeof payload.topicRevision !== 'number') return false;
    const current = this.latestProjectionRevision.get(payload.topic);
    if (typeof current === 'number' && payload.topicRevision <= current) return true;
    this.latestProjectionRevision.set(payload.topic, payload.topicRevision);
    return false;
  }

  private startHeartbeat(): void { this.stopHeartbeat(); this.heartbeatTimer = window.setInterval(() => { this.send('client.ping', { sentAt: new Date().toISOString() }); this.emit('connection.heartbeat', { timestamp: new Date().toISOString() }); }, this.heartbeatIntervalMs); }
  private stopHeartbeat(): void { if (this.heartbeatTimer) { window.clearInterval(this.heartbeatTimer); this.heartbeatTimer = null; } }
  private scheduleReconnect(): void { if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer); this.reconnectAttempts += 1; const base = Math.min(1500 * 2 ** (this.reconnectAttempts - 1), this.maxReconnectDelayMs); const jitter = Math.round(Math.random() * 400); const delay = base + jitter; this.emit('connection.reconnect_scheduled', { attempt: this.reconnectAttempts, delayMs: delay, timestamp: new Date().toISOString() }); this.reconnectTimer = window.setTimeout(() => this.connect(), delay); }
}
