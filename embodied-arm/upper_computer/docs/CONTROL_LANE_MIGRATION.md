# Control Lane Migration

## Canonical launch entry points

- `ros2 launch arm_bringup runtime.launch.py runtime_lane:=sim_preview`
- `ros2 launch arm_bringup runtime.launch.py runtime_lane:=sim_authoritative`
- `ros2 launch arm_bringup runtime.launch.py runtime_lane:=real_preview`
- `ros2 launch arm_bringup runtime_real_candidate.launch.py`
- `ros2 launch arm_bringup runtime_real_validated_live.launch.py`
- `ros2 launch arm_bringup runtime_real_authoritative.launch.py` *(compatibility alias -> `real_candidate`)*

## real_candidate / real_validated_live semantics

`real_candidate` is the validated-live candidate lane; `real_validated_live` is the promotion-controlled validated lane, not an unconditional live-production lane. It is only promoted above preview tier when all of the following are true:

1. `planning_capability=validated_live`
2. a live planning backend is explicitly injected into `MoveItClient`
3. readiness reports `planner_ready=true`
4. command policy allows `startTask`
5. hardware transport is not simulated
6. `config/runtime_promotion_receipts.yaml` commits `validated_live.promoted=true` with traceable evidence

If any of the above is false, the lane remains preview-tier and task execution stays non-interactive. This is a deliberate fail-closed contract to avoid representing unavailable live planning as operator-ready.

## Rollback

To roll back from `real_candidate` / `real_validated_live`, switch back to:

- `real_preview` for live camera / hardware preview work
- `sim_authoritative` for fully validated simulation execution

No code change is required; lane selection alone is sufficient.
