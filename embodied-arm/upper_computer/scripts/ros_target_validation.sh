#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_DIR="${ROOT_DIR}/backend/embodied_arm_ws"
ROS_SETUP="${ROS_SETUP:-/opt/ros/humble/setup.bash}"
ARTIFACT_DIR="${ROOT_DIR}/artifacts"
ENV_REPORT="${ARTIFACT_DIR}/target_env_report.json"
GATE_REPORT="${ARTIFACT_DIR}/release_gates/target_runtime_gate.json"
RELEASE_EVIDENCE="${ARTIFACT_DIR}/release_gates/release_evidence.json"

mkdir -p "${ARTIFACT_DIR}" "${ARTIFACT_DIR}/release_gates" "${ARTIFACT_DIR}/hil"

ENV_STATUS="not_executed"
ROS_BUILD_STATUS="not_executed"
ROS_SMOKE_STATUS="not_executed"
NEGATIVE_PATH_STATUS="not_executed"
HIL_STATUS="not_executed"
REPO_GATE_STATUS="not_executed"
RELEASE_CHECKLIST_STATUS="not_executed"
CURRENT_STEP="env"

write_gate_report() {
  python "${ROOT_DIR}/scripts/write_release_gate_report.py" \
    --env-report "${ENV_REPORT}" \
    --out "${GATE_REPORT}" \
    --evidence-path "${RELEASE_EVIDENCE}" \
    --step repo_gate="${REPO_GATE_STATUS}" \
    --step env="${ENV_STATUS}" \
    --step ros_build="${ROS_BUILD_STATUS}" \
    --step ros_smoke="${ROS_SMOKE_STATUS}" \
    --step negative_path_subset="${NEGATIVE_PATH_STATUS}" \
    --step hil="${HIL_STATUS}" \
    --step release_checklist="${RELEASE_CHECKLIST_STATUS}" >/dev/null
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
  python "${ROOT_DIR}/scripts/collect_release_evidence.py" --out "${RELEASE_EVIDENCE}" >/dev/null || true
  write_gate_report
  exit "${exit_code}"
}
trap 'finalize "$?"' EXIT

CURRENT_STEP="repo_gate"
REPO_SUMMARY="${ARTIFACT_DIR}/repository_validation/repo/verification_summary.json"
if [[ -f "${REPO_SUMMARY}" ]] && python - <<'PY' "${REPO_SUMMARY}" >/dev/null 2>&1
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding='utf-8'))
assert payload.get('profile') == 'repo'
assert payload.get('overallStatus') == 'passed'
required = payload.get('requiredSteps') or []
statuses = payload.get('stepStatuses') or {}
assert required
for name in required:
    assert statuses.get(name) == 'passed'
PY
then
  REPO_GATE_STATUS="passed"
else
  REPO_GATE_STATUS="not_executed"
fi

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
RELEASE_CHECKLIST_STATUS="not_executed"
