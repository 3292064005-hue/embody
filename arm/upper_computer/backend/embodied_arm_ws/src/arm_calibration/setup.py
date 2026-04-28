from setuptools import setup
package_name = 'arm_calibration'
setup(
    name=package_name,
    version='0.2.0',
    packages=[package_name],
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]),('share/' + package_name, ['package.xml'])],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='OpenAI',
    maintainer_email='dev@example.com',
    description='Calibration manager and transform helpers.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={'console_scripts': ['calibration_manager_node = arm_calibration.calibration_manager_node:main','calibration_node = arm_calibration.calibration_node:main']},
)
