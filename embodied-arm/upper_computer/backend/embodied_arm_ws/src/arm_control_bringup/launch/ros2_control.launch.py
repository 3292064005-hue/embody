from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    use_fake_hardware = LaunchConfiguration('use_fake_hardware')
    controller_config = LaunchConfiguration('controller_config')
    hardware_plugin = LaunchConfiguration('hardware_plugin')
    description_share = FindPackageShare('arm_description')
    robot_description = {
        'robot_description': Command([
            'xacro ',
            PathJoinSubstitution([description_share, 'urdf', 'arm.urdf.xacro']),
            ' use_fake_hardware:=', use_fake_hardware,
            ' hardware_plugin:=', hardware_plugin,
        ])
    }
    return LaunchDescription([
        DeclareLaunchArgument('use_fake_hardware', default_value='true'),
        DeclareLaunchArgument('controller_config', default_value=PathJoinSubstitution([FindPackageShare('arm_control_bringup'), 'config', 'controllers.yaml'])),
        DeclareLaunchArgument('hardware_plugin', default_value='arm_hardware_interface/EmbodiedArmSystemInterface'),
        Node(
            package='controller_manager',
            executable='ros2_control_node',
            parameters=[robot_description, controller_config],
            output='screen',
        ),
        Node(
            package='controller_manager',
            executable='spawner',
            arguments=['joint_state_broadcaster', '--controller-manager', '/controller_manager'],
            output='screen',
        ),
        Node(
            package='controller_manager',
            executable='spawner',
            arguments=['arm_joint_trajectory_controller', '--controller-manager', '/controller_manager'],
            output='screen',
        ),
        Node(
            package='controller_manager',
            executable='spawner',
            arguments=['gripper_command_controller', '--controller-manager', '/controller_manager'],
            output='screen',
        ),
    ])
