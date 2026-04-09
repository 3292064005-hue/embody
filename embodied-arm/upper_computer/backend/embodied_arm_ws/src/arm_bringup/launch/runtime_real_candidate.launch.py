"""Canonical candidate real-hardware runtime lane."""

from arm_bringup.launch_factory import build_runtime_launch_description


def generate_launch_description():
    return build_runtime_launch_description('real_candidate')
