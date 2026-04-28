from setuptools import setup

package_name = 'arm_esp32_gateway'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', ['config/gateway.yaml', 'config/voice_commands.yaml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='OpenAI',
    maintainer_email='dev@example.com',
    description='ESP32 gateway ROS package for board health and voice event ingestion.',
    license='MIT',
    entry_points={'console_scripts': ['esp32_gateway_node = arm_esp32_gateway.esp32_gateway_node:main']},
)
