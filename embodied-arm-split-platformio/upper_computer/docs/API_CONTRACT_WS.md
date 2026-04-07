# WebSocket Contract

The gateway publishes state and event updates to connected HMI clients.

## Envelope

```json
{
  "event": "task.progress.updated",
  "timestamp": "2026-03-31T12:00:00Z",
  "seq": 1234,
  "schemaVersion": "1.1",
  "snapshotVersion": 1,
  "bootstrapComplete": false,
  "deliveryMode": "snapshot",
  "topic": "task",
  "topicRevision": 7,
  "data": {}
}
```

## Initial snapshot
A newly connected client receives a private bootstrap snapshot. It must not be broadcast to other clients. Each bootstrap envelope carries `snapshotVersion`, `deliveryMode="snapshot"`, and the current per-topic `topicRevision`. The final bootstrap event sets `bootstrapComplete=true` on the envelope so the client can atomically enter live mode without waiting for a separate extra frame.

## Live delta updates
Runtime projection updates are broadcast with `deliveryMode="delta"`. Non-projection events such as audit/log/heartbeat remain `deliveryMode="event"`. Clients must de-duplicate projection frames by `topic + topicRevision` so late replays or bootstrap/pending interleaving cannot overwrite fresher state.

## Event types
- `system.state.updated`
- `hardware.state.updated`
- `task.progress.updated`
- `vision.targets.updated`
- `readiness.state.updated`
- `diagnostics.summary.updated`
- `calibration.profile.updated`
- `log.event.created`
- `audit.event.created`
- `server.pong`

## Replay
The gateway may replay a bounded number of recent events to new clients after the initial snapshot.

## Delivery rules
- publish order is monotonic per process
- slow clients are isolated through per-connection queues and a connection-level bootstrap barrier
- high-risk command responses are delivered over REST, not WebSocket
