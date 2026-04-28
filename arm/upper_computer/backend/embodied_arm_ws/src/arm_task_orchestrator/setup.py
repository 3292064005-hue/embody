from setuptools import find_packages, setup
package_name='arm_task_orchestrator'
setup(
    name=package_name,
    version='0.2.0',
    packages=find_packages(exclude=['test']),
    data_files=[('share/ament_index/resource_index/packages',['resource/'+package_name]),('share/'+package_name,['package.xml'])],
    install_requires=['setuptools'],
    zip_safe=True,
    entry_points={'console_scripts':['task_orchestrator = arm_task_orchestrator.orchestrator_node:main','task_orchestrator_node = arm_task_orchestrator.task_orchestrator_node:main']},
)
