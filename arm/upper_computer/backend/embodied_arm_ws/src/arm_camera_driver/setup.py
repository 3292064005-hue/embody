from setuptools import find_packages, setup
from glob import glob
package_name='arm_camera_driver'
setup(
    name=package_name,
    version='0.2.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',['resource/'+package_name]),
        ('share/'+package_name,['package.xml']),
        ('share/'+package_name+'/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    entry_points={'console_scripts': ['camera_driver = arm_camera_driver.camera_runtime_node:main']},
)
