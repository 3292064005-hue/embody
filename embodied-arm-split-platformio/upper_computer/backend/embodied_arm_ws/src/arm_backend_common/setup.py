from setuptools import setup

package_name = 'arm_backend_common'

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
    description='Common utilities for embodied arm backend.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [

        ],
    },
)
