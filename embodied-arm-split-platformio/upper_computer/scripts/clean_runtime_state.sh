#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_ROOT="${EMBODIED_ARM_STATE_ROOT:-${XDG_STATE_HOME:-$HOME/.local/state}/embodied-arm}"
rm -rf "${STATE_ROOT}/gateway_data" "${STATE_ROOT}/gateway_observability"
rm -rf "${ROOT_DIR}/gateway_data" "${ROOT_DIR}/artifacts/gateway_observability"
echo "cleaned runtime state roots: ${STATE_ROOT} and legacy repo paths"
