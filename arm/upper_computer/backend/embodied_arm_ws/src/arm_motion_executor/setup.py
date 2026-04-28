from setuptools import setup

package_name = 'arm_motion_executor'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='OpenAI',
    maintainer_email='dev@example.com',
    description='Embodied arm package: arm_motion_executor.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'motion_executor_node = arm_motion_executor.motion_executor_node:main'
        ]
    },
)
