#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"
LOCKFILE="${FRONTEND_DIR}/package-lock.json"


ORIGINAL_NPM_REGISTRY="${NPM_CONFIG_REGISTRY:-${npm_config_registry:-}}"
export NPM_CONFIG_USERCONFIG="${FRONTEND_DIR}/.npmrc"
export NPM_CONFIG_REGISTRY="https://registry.npmjs.org/"
unset NODE_AUTH_TOKEN NPM_TOKEN NPM_CONFIG__AUTH NPM_CONFIG__AUTH_TOKEN npm_config__auth npm_config__auth_token || true
SELECTED_REGISTRY="${FRONTEND_NPM_REGISTRY:-${ORIGINAL_NPM_REGISTRY:-${NPM_CONFIG_REGISTRY}}}"
export NPM_CONFIG_REGISTRY="${SELECTED_REGISTRY}"
export npm_config_registry="${SELECTED_REGISTRY}"
export NPM_CONFIG_GLOBALCONFIG=/dev/null
cd "${FRONTEND_DIR}"

normalize_lockfile_registry() {
  python - "${LOCKFILE}" "${SELECTED_REGISTRY}" <<'PY'
from pathlib import Path
import sys

lockfile = Path(sys.argv[1])
registry = sys.argv[2].rstrip('/') + '/'
text = lockfile.read_text(encoding='utf-8')
internal_prefix = 'https://packages.applied-caas-gateway1.internal.api.openai.org/artifactory/api/npm/npm-public/'
public_prefix = 'https://registry.npmjs.org/'

if registry == public_prefix:
    updated = text.replace(internal_prefix, public_prefix)
else:
    updated = text.replace(public_prefix, registry).replace(internal_prefix, registry)

if updated != text:
    lockfile.write_text(updated, encoding='utf-8')
PY
}

ensure_bin_link() {
  local name="$1"
  local target="$2"
  if [[ ! -f "${target}" ]]; then
    return 0
  fi
  mkdir -p node_modules/.bin
  ln -sf "../${target#node_modules/}" "node_modules/.bin/${name}"
  chmod +x "node_modules/.bin/${name}" || true
}

ensure_tool_bins() {
  ensure_bin_link vue-tsc node_modules/vue-tsc/bin/vue-tsc.js
  ensure_bin_link vite node_modules/vite/bin/vite.js
  ensure_bin_link vitest node_modules/vitest/vitest.mjs
  ensure_bin_link playwright node_modules/playwright/cli.js
}

needs_install=0

if [[ ! -f package-lock.json ]]; then
  echo "frontend dependency bootstrap requires package-lock.json" >&2
  exit 1
fi

normalize_lockfile_registry

if [[ ! -d node_modules ]]; then
  needs_install=1
elif [[ ! -f node_modules/vue-tsc/index.js ]]; then
  needs_install=1
elif [[ ! -f node_modules/vite/bin/vite.js ]]; then
  needs_install=1
else
  ensure_tool_bins
  if [[ ! -e node_modules/.bin/vue-tsc ]]; then
    needs_install=1
  elif ! node node_modules/vue-tsc/index.js --version >/dev/null 2>&1; then
    needs_install=1
  elif ! node node_modules/vite/bin/vite.js --version >/dev/null 2>&1; then
    needs_install=1
  fi
fi

if [[ "${needs_install}" -eq 1 ]]; then
  echo "[frontend] installing dependencies with npm ci (registry: ${SELECTED_REGISTRY})"
  npm ci --userconfig "${NPM_CONFIG_USERCONFIG}" --registry "${NPM_CONFIG_REGISTRY}"
  ensure_tool_bins
fi
