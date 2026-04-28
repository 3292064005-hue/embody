from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    publish_robot_description = LaunchConfiguration('publish_robot_description')
    return LaunchDescription([
        DeclareLaunchArgument('publish_robot_description', default_value='true'),
        LogInfo(msg='arm_description: description launch prepared'),
        LogInfo(condition=IfCondition(publish_robot_description), msg='robot description publication requested'),
    ])
