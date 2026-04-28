from setuptools import setup
package_name='arm_readiness_manager'
setup(name=package_name, version='0.1.0', packages=[package_name], data_files=[('share/ament_index/resource_index/packages',['resource/'+package_name]),('share/'+package_name,['package.xml'])], install_requires=['setuptools'], zip_safe=True, entry_points={'console_scripts':['readiness_manager_node = arm_readiness_manager.readiness_manager_node:main','mode_coordinator_node = arm_readiness_manager.mode_coordinator_node:main']})
