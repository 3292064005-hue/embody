"""Compatibility wrapper for the live-control experimental runtime lane."""

from arm_bringup.launch_factory import build_runtime_launch_description


def generate_launch_description():
    return build_runtime_launch_description('live_control')
