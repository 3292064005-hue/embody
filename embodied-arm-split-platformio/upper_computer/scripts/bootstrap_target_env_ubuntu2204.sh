#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "[bootstrap] please run as root: sudo bash scripts/bootstrap_target_env_ubuntu2204.sh" >&2
  exit 1
fi

if [[ ! -f /etc/os-release ]]; then
  echo "[bootstrap] /etc/os-release not found" >&2
  exit 1
fi

# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "22.04" ]]; then
  echo "[bootstrap] this script only supports Ubuntu 22.04" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends   ca-certificates   curl   gnupg   lsb-release   software-properties-common   build-essential   git   python3.10   python3.10-venv   python3-pip

install -d -m 0755 /etc/apt/keyrings
if [[ ! -f /etc/apt/keyrings/nodesource.gpg ]]; then
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
fi
cat >/etc/apt/sources.list.d/nodesource.list <<'EOF'
deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main
EOF

if [[ ! -f /etc/apt/keyrings/ros-archive-keyring.gpg ]]; then
  curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key | gpg --dearmor -o /etc/apt/keyrings/ros-archive-keyring.gpg
fi
cat >/etc/apt/sources.list.d/ros2.list <<'EOF'
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu jammy main
EOF

apt-get update
apt-get install -y --no-install-recommends   nodejs   ros-humble-desktop   python3-colcon-common-extensions   python3-rosdep   python3-vcstool

npm install -g npm@10.9.2
rosdep init || true
su - "${SUDO_USER:-$(logname 2>/dev/null || echo root)}" -c 'rosdep update' || rosdep update

echo "[bootstrap] target environment bootstrap complete"
echo "[bootstrap] next steps:"
echo "  1) python3.10 -m pip install -r gateway/requirements.txt pytest"
echo "  2) cd frontend && npm ci"
echo "  3) make target-env-check"
echo "  4) make ros-target-validate"
