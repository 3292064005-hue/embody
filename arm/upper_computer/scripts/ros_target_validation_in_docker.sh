#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_TAG="${ROS_TARGET_DOCKER_IMAGE:-embodied-arm-target-env:humble}"
DOCKERFILE_PATH="${ROOT_DIR}/docker/target_env_validation.Dockerfile"

if ! command -v docker >/dev/null 2>&1; then
  echo "[ros-target-validate-docker] docker is required but not found on PATH" >&2
  exit 1
fi

if [[ ! -f "${DOCKERFILE_PATH}" ]]; then
  echo "[ros-target-validate-docker] Dockerfile not found: ${DOCKERFILE_PATH}" >&2
  exit 1
fi

docker build -f "${DOCKERFILE_PATH}" -t "${IMAGE_TAG}" "${ROOT_DIR}"
docker run --rm -t \
  -e ROS_SETUP=/opt/ros/humble/setup.bash \
  -e NPM_CONFIG_REGISTRY=https://registry.npmjs.org/ \
  -v "${ROOT_DIR}:/workspace" \
  -w /workspace \
  "${IMAGE_TAG}" \
  bash -lc 'python scripts/check_target_env.py --strict && bash scripts/ros_target_validation.sh'
