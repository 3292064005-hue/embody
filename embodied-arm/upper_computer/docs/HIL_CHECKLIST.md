# Hardware-in-the-Loop Checklist

Machine-readable counterpart: `artifacts/hil/hil_checklist.json`

## Smoke tests
- power on and heartbeat visible
- home sequence
- manual jog
- servo cartesian micro-adjust
- gripper open/close
- emergency stop
- reset fault
- target clear and reload vision
- one complete pick-place cycle

## Failure-path tests
- cable disconnect during idle
- cable disconnect during execution
- stale readiness transition
- camera offline during task start
- limit / estop event during motion

## Reporting rule
- If HIL was not executed, mark the gate as `not_executed` rather than implying success.
- Release reports must distinguish repository pass, target-runtime pass, and HIL execution evidence.
