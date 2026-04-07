"""Compatibility alias for the canonical runtime_sim lane.

This launch file is kept for backward compatibility only. New validation and
operator-facing documentation must use `runtime_sim.launch.py` explicitly.
"""

from arm_bringup.launch_factory import build_official_runtime_launch_description


def generate_launch_description():
    return build_official_runtime_launch_description('official_runtime')
