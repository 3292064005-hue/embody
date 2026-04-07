from setuptools import setup
package_name='arm_hmi'
setup(
    name=package_name,
    version='0.2.0',
    packages=[package_name],
    data_files=[('share/ament_index/resource_index/packages',['resource/'+package_name]),('share/'+package_name,['package.xml'])],
    install_requires=['setuptools'],
    zip_safe=True,
    entry_points={'console_scripts':['arm_hmi = arm_hmi.hmi_node:main']},
)
