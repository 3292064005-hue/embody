from setuptools import find_packages, setup
package_name='arm_scene_manager'
setup(
    name=package_name,
    version='0.2.0',
    packages=find_packages(exclude=['test']),
    data_files=[('share/ament_index/resource_index/packages',['resource/'+package_name]),('share/'+package_name,['package.xml'])],
    install_requires=['setuptools'],
    zip_safe=True,
    entry_points={'console_scripts':['scene_manager = arm_scene_manager.scene_manager_node:main']},
)
