# validated_live evidence bundle

This directory stores repository-tracked evidence required before the `validated_live`
product line can be promoted above `preview`.

Rules:

- Repository-level checks may generate or update metadata, but they must not mark a gate
  as passed unless the corresponding target-runtime evidence has been produced.
- `hil_smoke_report.md` and `release_checklist.md` are authoritative operator sign-off
  artifacts. Until both are marked as passed and the runtime authority declares the live
  planning backend plus the ros2_control execution backbone, `validated_live` stays
  fail-closed.
- Promotion receipts alone are insufficient. The receipt markers must match the evidence
  manifest in `backend/embodied_arm_ws/src/arm_bringup/config/validated_live_evidence.yaml`.
