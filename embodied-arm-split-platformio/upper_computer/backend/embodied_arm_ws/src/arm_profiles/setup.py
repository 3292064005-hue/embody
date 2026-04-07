from setuptools import setup

package_name = 'arm_profiles'

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
    description='Task and placement profile manager.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'profile_manager_node = arm_profiles.profile_manager_node:main',
        ],
    },
)
