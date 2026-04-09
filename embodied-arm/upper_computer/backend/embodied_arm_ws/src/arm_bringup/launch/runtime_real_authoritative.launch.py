"""Compatibility wrapper for the retired real_authoritative lane.

The historic `real_authoritative` entry now resolves to the explicit
`real_candidate` lane so older operator scripts keep working without creating a
second live lane truth source.
"""

from arm_bringup.launch_factory import build_runtime_launch_description


def generate_launch_description():
    return build_runtime_launch_description('real_candidate')
