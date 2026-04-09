# Compatibility Regression Evidence

These suites remain useful for historical regression containment but **must not** be cited as active release proof while the corresponding packages remain compatibility-only or deprecated.

- `backend/embodied_arm_ws/tests/test_queue_and_reservation.py`
- `backend/embodied_arm_ws/tests/test_readiness_and_planning.py`
- `backend/embodied_arm_ws/tests/test_split_stack_runtime.py`
- `backend/embodied_arm_ws/tests/test_verification.py`

These paths are mirrored in `backend/embodied_arm_ws/active_profile_quarantine.json`. Release reports should always separate:

1. active runtime pass
2. compatibility regression pass

Do not merge them into a single P0 / P1 traceability statement.
