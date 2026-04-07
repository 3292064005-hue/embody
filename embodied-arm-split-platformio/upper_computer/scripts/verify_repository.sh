#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend/embodied_arm_ws"
FRONTEND_DIR="${ROOT_DIR}/frontend"
ARTIFACT_DIR="${ROOT_DIR}/artifacts/repository_validation"
mkdir -p "${ARTIFACT_DIR}"

run_step() {
  local name="$1"
  shift
  local log_path="${ARTIFACT_DIR}/${name}.log"
  echo "[verify] ${name}"
  if "$@" >"${log_path}" 2>&1; then
    echo "[verify] ${name}: passed"
  else
    local exit_code="$?"
    echo "[verify] ${name}: failed (see ${log_path})" >&2
    tail -n 200 "${log_path}" >&2 || true
    return "${exit_code}"
  fi
}

run_step backend-active bash -lc "cd '${BACKEND_DIR}' && python -m pytest -q -c pytest-active.ini"
run_step active-profile-consistency python "${ROOT_DIR}/scripts/check_active_profile_consistency.py"
run_step contract-artifacts python "${ROOT_DIR}/scripts/generate_contract_artifacts.py" --check
run_step gateway bash -lc "cd '${ROOT_DIR}' && python -m pytest -q gateway/tests"
run_step frontend-stack bash -lc "cd '${ROOT_DIR}' && bash scripts/ensure_frontend_deps.sh && cd '${FRONTEND_DIR}' && ./node_modules/.bin/vue-tsc --noEmit && ./node_modules/.bin/vitest run --pool=threads --maxWorkers=1 && ./node_modules/.bin/vite build && node ./scripts/run-playwright-e2e.mjs"
run_step audit python "${ROOT_DIR}/scripts/final_audit.py"
