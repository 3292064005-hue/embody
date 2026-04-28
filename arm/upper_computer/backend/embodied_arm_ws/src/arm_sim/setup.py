from setuptools import setup
package_name='arm_sim'
setup(
    name=package_name,
    version='0.2.0',
    packages=[package_name],
    data_files=[('share/ament_index/resource_index/packages',['resource/'+package_name]),('share/'+package_name,['package.xml'])],
    install_requires=['setuptools'],
    zip_safe=True,
    entry_points={'console_scripts':['fake_hardware = arm_sim.fake_hardware_node:main']},
)
