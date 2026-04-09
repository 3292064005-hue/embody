export type WsState = 'idle' | 'connecting' | 'open' | 'closing' | 'closed' | 'error';
export type ConnectionQuality = 'healthy' | 'degraded' | 'offline';
export type TransportState = 'bootstrapping' | 'live' | 'degraded' | 'resyncing';

export interface ConnectionHealth {
  wsState: WsState;
  gatewayConnected: boolean;
  lastHeartbeatAt: string;
  lastMessageAt: string;
  lastPongAt: string;
  lastServerSyncAt: string;
  lastEventName: string;
  latencyMs: number | null;
  reconnectAttempts: number;
  parseErrors: number;
  syncErrors: number;
  staleAfterMs: number;
  readonlyDegraded: boolean;
  transportState: TransportState;
}
