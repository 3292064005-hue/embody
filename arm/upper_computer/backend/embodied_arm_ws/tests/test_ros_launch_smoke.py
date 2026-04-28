from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import pytest

WORKSPACE = Path(__file__).resolve().parents[1]
ROS_SETUP = Path(os.environ.get('ROS_SETUP', '/opt/ros/humble/setup.bash'))


def _ros_runtime_available() -> bool:
    return shutil.which('ros2') is not None and shutil.which('colcon') is not None and ROS_SETUP.exists()


def _workspace_install_ready() -> bool:
    return (WORKSPACE / 'install' / 'setup.bash').exists()


def _ros_node_list() -> list[str]:
    command = (
        f"set -euo pipefail; source '{ROS_SETUP}'; source '{WORKSPACE / 'install' / 'setup.bash'}'; "
        'ros2 node list'
    )
    completed = subprocess.run(
        ['bash', '-lc', command],
        cwd=str(WORKSPACE),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _wait_for_runtime_nodes(timeout_sec: float = 8.0) -> list[str]:
    expected = {
        '/hardware_state_aggregator_node',
        '/hardware_command_dispatcher',
        '/readiness_manager',
        '/task_orchestrator',
        '/motion_planner_node',
        '/motion_executor_node',
        '/scene_manager',
        '/grasp_planner',
        '/stm32_serial_node',
    }
    start = time.monotonic()
    last_nodes: list[str] = []
    while time.monotonic() - start < timeout_sec:
        last_nodes = _ros_node_list()
        if len(expected.intersection(last_nodes)) >= 3:
            return last_nodes
        time.sleep(0.25)
    return last_nodes


@pytest.mark.skipif(not _ros_runtime_available(), reason='ROS2 / colcon runtime unavailable in this environment')
def test_runtime_sim_launch_smoke_real_ros_runtime() -> None:
    if not _workspace_install_ready():
        pytest.skip('workspace install/setup.bash missing; run colcon build first')

    command = (
        f"set -euo pipefail; source '{ROS_SETUP}'; source '{WORKSPACE / 'install' / 'setup.bash'}'; "
        f"cd '{WORKSPACE}'; "
        'ros2 launch arm_bringup runtime_sim.launch.py enable_moveit:=false enable_rviz:=false camera_source:=mock'
    )
    process: subprocess.Popen[str] | None = None
    output = ''
    try:
        process = subprocess.Popen(
            ['bash', '-lc', command],
            cwd=str(WORKSPACE),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        nodes = _wait_for_runtime_nodes()
        assert len(nodes) >= 3, f'expected runtime-core nodes to register, observed: {nodes}'
    finally:
        if process is not None:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=10.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5.0)
            output = process.stdout.read() if process.stdout is not None else ''
            if process.returncode not in (0, -signal.SIGINT, 130):
                pytest.fail(f'runtime_sim launch exited unexpectedly with code {process.returncode}\n{output}')
            assert 'Traceback' not in output
            assert 'ModuleNotFoundError' not in output
            assert 'package not found' not in output.lower()
