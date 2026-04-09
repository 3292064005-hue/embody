from setuptools import setup

package_name = 'arm_hardware_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools', 'pyserial>=3.5'],
    zip_safe=True,
    maintainer='OpenAI',
    maintainer_email='dev@example.com',
    description='STM32 and ESP32 bridge nodes.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'stm32_serial_node = arm_hardware_bridge.stm32_serial_node:main',
            'esp32_link_node = arm_hardware_bridge.esp32_link_node:main',
            'hardware_state_aggregator_node = arm_hardware_bridge.hardware_state_aggregator_node:main',
            'hardware_command_dispatcher_node = arm_hardware_bridge.hardware_command_dispatcher_node:main',
        ],
    },
)
