from setuptools import setup

package_name = 'arm_safety_supervisor'

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
    description='Safety supervision and stop/fault gating.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={'console_scripts': ['safety_supervisor_node = arm_safety_supervisor.safety_supervisor_node:main']},
)
