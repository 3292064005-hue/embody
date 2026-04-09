#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${ROOT_DIR}/artifacts/split_repository_validation"
mkdir -p "${ARTIFACT_DIR}"

run_step() {
  local name="$1"
  shift
  local log_path="${ARTIFACT_DIR}/${name}.log"
  echo "[split-verify] ${name}"
  if "$@" >"${log_path}" 2>&1; then
    echo "[split-verify] ${name}: passed"
  else
    local exit_code="$?"
    echo "[split-verify] ${name}: failed (see ${log_path})" >&2
    tail -n 200 "${log_path}" >&2 || true
    return "${exit_code}"
  fi
}

run_step upper-computer bash -lc "cd '${ROOT_DIR}/upper_computer' && bash scripts/verify_repository.sh --profile fast"
run_step firmware-source-contracts python "${ROOT_DIR}/scripts/verify_firmware_sources.py"

ESP32_PLATFORM_DIR="${HOME}/.platformio/platforms/espressif32"
STM32_PLATFORM_DIR="${HOME}/.platformio/platforms/ststm32"
if command -v pio >/dev/null 2>&1 && [[ -d "${ESP32_PLATFORM_DIR}" && -d "${STM32_PLATFORM_DIR}" ]]; then
  run_step esp32-build bash -lc "cd '${ROOT_DIR}/esp32s3_platformio' && timeout 20m pio run"
  run_step stm32-build bash -lc "cd '${ROOT_DIR}/stm32f103c8_platformio' && timeout 20m pio run"
elif [[ "${SPLIT_VERIFY_REQUIRE_FIRMWARE_BUILD:-0}" == "1" ]]; then
  echo '[split-verify] firmware build required but local PlatformIO platform packages are unavailable.' >&2
  exit 1
else
  echo '[split-verify] local firmware source contracts passed; PlatformIO platform packages are unavailable, so actual firmware builds are deferred to CI or to a connected workstation.' | tee "${ARTIFACT_DIR}/platformio-build-deferred.log"
fi
run_step release-manifest python "${ROOT_DIR}/scripts/package_split_release.py" --check
