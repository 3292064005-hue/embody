import { defineStore } from 'pinia';
import type { ConnectionHealth, ConnectionQuality, TransportState, WsState } from '@/models/connection';

export const useConnectionStore = defineStore('connection', {
  state: (): ConnectionHealth => ({
    wsState: 'idle',
    gatewayConnected: false,
    lastHeartbeatAt: '',
    lastMessageAt: '',
    lastPongAt: '',
    lastServerSyncAt: '',
    lastEventName: '',
    latencyMs: null,
    reconnectAttempts: 0,
    parseErrors: 0,
    syncErrors: 0,
    staleAfterMs: 8000,
    readonlyDegraded: false,
    transportState: 'bootstrapping',
  }),
  getters: {
    isRealtimeStale(state): boolean {
      if (!state.lastMessageAt) return true;
      return Date.now() - new Date(state.lastMessageAt).getTime() > state.staleAfterMs;
    },
    quality(state): ConnectionQuality {
      if (!state.gatewayConnected || state.wsState === 'closed' || state.wsState === 'error') return 'offline';
      if (this.isRealtimeStale || state.parseErrors > 0 || state.syncErrors > 0 || state.transportState === 'degraded') return 'degraded';
      return 'healthy';
    },
    healthBadge(): 'success' | 'warning' | 'danger' {
      if (this.quality === 'offline') return 'danger';
      if (this.quality === 'degraded') return 'warning';
      return 'success';
    }
  },
  actions: {
    setWsState(state: WsState) { this.wsState = state; },
    setGatewayConnected(connected: boolean) { this.gatewayConnected = connected; },
    setTransportState(state: TransportState) { this.transportState = state; },
    markHeartbeat(timestamp: string) { this.lastHeartbeatAt = timestamp; },
    markPong(timestamp: string) { this.lastPongAt = timestamp; },
    markMessage(timestamp: string, latencyMs?: number | null, eventName?: string) {
      this.lastMessageAt = timestamp;
      if (typeof latencyMs === 'number') this.latencyMs = latencyMs;
      if (eventName) this.lastEventName = eventName;
      if (this.transportState !== 'resyncing') this.transportState = 'live';
    },
    markServerSync(timestamp: string, eventName?: string) {
      this.lastServerSyncAt = timestamp;
      if (eventName) this.lastEventName = eventName;
      this.syncErrors = 0;
      if (this.transportState === 'bootstrapping' || this.transportState === 'resyncing') {
        this.transportState = this.gatewayConnected ? 'live' : this.transportState;
      }
    },
    incrementReconnect() {
      this.reconnectAttempts += 1;
      this.transportState = 'resyncing';
    },
    incrementParseErrors() {
      this.parseErrors += 1;
      this.transportState = 'degraded';
    },
    incrementSyncError() {
      this.syncErrors += 1;
      if (this.gatewayConnected) this.transportState = 'degraded';
    },
    setStaleAfterMs(value: number) { this.staleAfterMs = value; },
    setReadonlyDegraded(value: boolean) {
      this.readonlyDegraded = value;
      if (value) this.transportState = 'degraded';
      else if (this.gatewayConnected && this.transportState === 'degraded') this.transportState = 'live';
    },
    resetSession() {
      this.wsState = 'idle';
      this.gatewayConnected = false;
      this.lastHeartbeatAt = '';
      this.lastMessageAt = '';
      this.lastPongAt = '';
      this.lastServerSyncAt = '';
      this.lastEventName = '';
      this.latencyMs = null;
      this.reconnectAttempts = 0;
      this.parseErrors = 0;
      this.syncErrors = 0;
      this.readonlyDegraded = false;
      this.transportState = 'bootstrapping';
    }
  }
});
