from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1] / 'src'
sys.path.insert(0, str(ROOT / 'arm_motion_planner'))

from arm_motion_planner.moveit_client import MoveItClient


def test_validated_live_backend_reports_not_ready_by_default() -> None:
    client = MoveItClient(capability_mode='validated_live', authoritative=True, backend_name='validated_live_bridge')
    assert client.planning_backend_ready() is False


def test_validated_sim_backend_reports_ready() -> None:
    client = MoveItClient(capability_mode='validated_sim', authoritative=True, backend_name='validated_sim_runtime')
    assert client.planning_backend_ready() is True
