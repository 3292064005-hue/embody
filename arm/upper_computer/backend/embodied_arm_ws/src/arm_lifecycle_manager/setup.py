from setuptools import find_packages, setup

package_name = 'arm_lifecycle_manager'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='OpenAI',
    maintainer_email='dev@example.com',
    description='Bringup readiness and lifecycle summary node.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'lifecycle_manager_node = arm_lifecycle_manager.lifecycle_manager_node:main',
            'runtime_supervisor_node = arm_lifecycle_manager.runtime_supervisor_node:main',
            'managed_lifecycle_manager_node = arm_lifecycle_manager.managed_lifecycle_manager_node:main',
        ],
    },
)
