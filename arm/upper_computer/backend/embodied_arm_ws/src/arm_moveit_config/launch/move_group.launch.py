from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    enable_rviz = LaunchConfiguration('enable_rviz')
    return LaunchDescription([
        DeclareLaunchArgument('enable_rviz', default_value='false'),
        LogInfo(msg='arm_moveit_config:move_group launch prepared'),
        LogInfo(condition=IfCondition(enable_rviz), msg='RViz requested for move_group launch'),
    ])
