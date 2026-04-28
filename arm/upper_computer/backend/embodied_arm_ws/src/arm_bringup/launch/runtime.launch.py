"""Canonical runtime entry with an explicit runtime_lane argument."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration

from arm_bringup.launch_factory import build_runtime_launch_description


def _runtime_setup(context, *_args, **_kwargs):
    lane = LaunchConfiguration('runtime_lane').perform(context)
    include_mock = LaunchConfiguration('include_mock_targets').perform(context).lower() == 'true'
    runtime_ld = build_runtime_launch_description(lane, include_mock_targets=include_mock)
    return list(runtime_ld.entities)


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('runtime_lane', default_value='sim_preview'),
        DeclareLaunchArgument('include_mock_targets', default_value='false'),
        OpaqueFunction(function=_runtime_setup),
    ])
