# Serial Protocol

The STM32 transport is a framed command protocol.

## Required fields
- `version`
- `command`
- `sequence`
- `requestId`
- `taskId`
- `stage`
- `payload`
- `checksum`

## Reliability rules
- commands are idempotent within a bounded deduplication window
- heartbeat is independent from task control
- emergency stop is independent from task stop
- malformed frames are rejected without side effects
- missing ACK transitions the executor to timeout/error handling

## Safety commands
- `ESTOP`
- `SAFE_HALT`
- `HOME`
- `JOG`
- `GRIPPER`
