.PHONY: test test-backend test-backend-active test-backend-active-consistency test-gateway test-frontend test-frontend-e2e audit lint verify package clean clean-runtime-state ros-build ros-smoke ros-smoke-sim ros-smoke-real ros-smoke-hybrid contract-test frontend-build target-env-check ros-target-validate target-env-bootstrap ros-target-validate-docker release-gate-report hil-template repo-gate target-gate hil-gate collect-release-evidence

ROOT := $(CURDIR)
BACKEND := $(ROOT)/backend/embodied_arm_ws
GATEWAY := $(ROOT)/gateway
FRONTEND := $(ROOT)/frontend
ROS_SETUP ?= /opt/ros/humble/setup.bash

verify:
	bash scripts/verify_repository.sh

test: verify

test-backend:
	cd $(BACKEND) && python -m pytest -q

test-backend-active:
	cd $(BACKEND) && python -m pytest -q -c pytest-active.ini

test-gateway:
	cd $(ROOT) && python -m pytest -q gateway/tests


test-backend-active-consistency:
	python scripts/check_active_profile_consistency.py


test-frontend:
	bash scripts/ensure_frontend_deps.sh
	cd $(FRONTEND) && npm run typecheck
	cd $(FRONTEND) && npm run test:unit

test-frontend-e2e:
	bash scripts/ensure_frontend_deps.sh
	cd $(FRONTEND) && npm run test:e2e

audit:
	python scripts/final_audit.py

frontend-build:
	bash scripts/ensure_frontend_deps.sh
	cd $(FRONTEND) && npm run build

package:
	python scripts/package_release.py

clean:
	find $(ROOT) -type d -name '__pycache__' -prune -exec rm -rf {} +
	find $(ROOT) -type d -name '.pytest_cache' -prune -exec rm -rf {} +

clean-runtime-state:
	bash scripts/clean_runtime_state.sh

ros-build:
	bash -lc 'set -euo pipefail; source "$(ROS_SETUP)"; cd "$(BACKEND)"; colcon build --symlink-install'

ros-smoke:
	bash -lc 'set -euo pipefail; source "$(ROS_SETUP)"; cd "$(BACKEND)"; test -f install/setup.bash || colcon build --symlink-install; source install/setup.bash; pytest -q tests/test_ros_launch_smoke.py tests/test_gateway_dispatcher_feedback_roundtrip.py'

ros-smoke-sim:
	bash -lc 'set -euo pipefail; source "$(ROS_SETUP)"; cd "$(BACKEND)"; test -f install/setup.bash || colcon build --symlink-install; source install/setup.bash; ros2 launch arm_bringup runtime_sim.launch.py enable_moveit:=false enable_rviz:=false camera_source:=mock'

ros-smoke-real:
	bash -lc 'set -euo pipefail; source "$(ROS_SETUP)"; cd "$(BACKEND)"; test -f install/setup.bash || colcon build --symlink-install; source install/setup.bash; ros2 launch arm_bringup runtime_real.launch.py enable_moveit:=false enable_rviz:=false camera_source:=topic'

ros-smoke-hybrid:
	bash -lc 'set -euo pipefail; source "$(ROS_SETUP)"; cd "$(BACKEND)"; test -f install/setup.bash || colcon build --symlink-install; source install/setup.bash; ros2 launch arm_bringup runtime_hybrid.launch.py enable_moveit:=false enable_rviz:=false camera_source:=topic'

target-env-check:
	python scripts/check_target_env.py --strict

ros-target-validate:
	bash scripts/ros_target_validation.sh

contract-test:
	pytest -q gateway/tests/test_server.py gateway/tests/test_runtime_contracts.py backend/embodied_arm_ws/tests/test_launch_integrity.py backend/embodied_arm_ws/tests/test_calibration_manager_node_instantiation.py backend/embodied_arm_ws/tests/test_ros_launch_smoke.py backend/embodied_arm_ws/tests/test_gateway_dispatcher_feedback_roundtrip.py


target-env-bootstrap:
	bash scripts/bootstrap_target_env_ubuntu2204.sh


ros-target-validate-docker:
	bash scripts/ros_target_validation_in_docker.sh

release-gate-report:
	python scripts/write_release_gate_report.py

hil-template:
	python scripts/write_hil_checklist_template.py

repo-gate:
	bash scripts/verify_repository.sh

target-gate:
	bash scripts/ros_target_validation.sh

hil-gate:
	python scripts/write_hil_checklist_template.py

collect-release-evidence:
	python scripts/collect_release_evidence.py
