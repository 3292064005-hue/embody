#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_DIR="${ROOT_DIR}/backend/embodied_arm_ws"
ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"
ARTIFACT_DIR="${ROOT_DIR}/artifacts"
ENV_REPORT="${ARTIFACT_DIR}/target_env_report.json"
GATE_REPORT="${ARTIFACT_DIR}/release_gates/target_runtime_gate.json"

mkdir -p "${ARTIFACT_DIR}" "${ARTIFACT_DIR}/release_gates" "${ARTIFACT_DIR}/hil"

ENV_STATUS="blocked"
ROS_BUILD_STATUS="blocked"
ROS_SMOKE_STATUS="blocked"
NEGATIVE_PATH_STATUS="blocked"
HIL_STATUS="not_executed"
REPO_GATE_STATUS="not_executed"
TARGET_GATE_STATUS="blocked"
CURRENT_STEP="env"

write_gate_report() {
  python "${ROOT_DIR}/scripts/write_release_gate_report.py"     --env-report "${ENV_REPORT}"     --out "${GATE_REPORT}"     --step repo_gate="${REPO_GATE_STATUS}"     --step target_gate="${TARGET_GATE_STATUS}"     --step env="${ENV_STATUS}"     --step ros_build="${ROS_BUILD_STATUS}"     --step ros_smoke="${ROS_SMOKE_STATUS}"     --step negative_path_subset="${NEGATIVE_PATH_STATUS}"     --step hil="${HIL_STATUS}" >/dev/null
}

finalize() {
  local exit_code="$1"
  if [[ "${exit_code}" -ne 0 ]]; then
    case "${CURRENT_STEP}" in
      env) ENV_STATUS="failed" ;;
      ros_build) ROS_BUILD_STATUS="failed" ;;
      ros_smoke) ROS_SMOKE_STATUS="failed" ;;
      negative_path_subset) NEGATIVE_PATH_STATUS="failed" ;;
      hil) HIL_STATUS="failed" ;;
    esac
  fi
  python "${ROOT_DIR}/scripts/write_hil_checklist_template.py" >/dev/null
  write_gate_report
  exit "${exit_code}"
}
trap 'finalize "$?"' EXIT

CURRENT_STEP="repo_gate"
REPO_GATE_STATUS="skipped"
CURRENT_STEP="env"
python "${ROOT_DIR}/scripts/check_target_env.py" --strict --ros-setup "${ROS_SETUP}" --output "${ENV_REPORT}" >/dev/null
ENV_STATUS="passed"

# shellcheck disable=SC1090
source "${ROS_SETUP}"
cd "${WORKSPACE_DIR}"
CURRENT_STEP="ros_build"
colcon build --symlink-install
ROS_BUILD_STATUS="passed"

source install/setup.bash
CURRENT_STEP="ros_smoke"
pytest -q tests/test_ros_launch_smoke.py tests/test_gateway_dispatcher_feedback_roundtrip.py
ROS_SMOKE_STATUS="passed"

CURRENT_STEP="negative_path_subset"
pytest -q tests/test_runtime_semantic_contracts.py tests/test_safety_policy.py
NEGATIVE_PATH_STATUS="passed"

CURRENT_STEP="hil"
HIL_STATUS="not_executed"
REPO_GATE_STATUS="not_executed"
TARGET_GATE_STATUS="blocked"
