from setuptools import setup
package_name = 'arm_diagnostics'
setup(
    name=package_name,
    version='0.2.0',
    packages=[package_name],
    data_files=[('share/ament_index/resource_index/packages', ['resource/' + package_name]),('share/' + package_name, ['package.xml'])],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='OpenAI',
    maintainer_email='dev@example.com',
    description='Runtime diagnostics summary node.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={'console_scripts': ['diagnostics_summary_node = arm_diagnostics.diagnostics_summary_node:main','diagnostics_node = arm_diagnostics.diagnostics_node:main']},
)
