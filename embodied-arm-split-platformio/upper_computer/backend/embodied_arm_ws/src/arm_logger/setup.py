from setuptools import setup
package_name = 'arm_logger'
setup(
    name=package_name,
    version='0.3.0',
    packages=[package_name],
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]),('share/' + package_name, ['package.xml'])],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='OpenAI',
    maintainer_email='dev@example.com',
    description='Event and metrics logging nodes.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={'console_scripts': ['event_logger_node = arm_logger.event_logger_node:main','metrics_logger_node = arm_logger.metrics_logger_node:main','event_logger = arm_logger.logger_node:main']},
)
