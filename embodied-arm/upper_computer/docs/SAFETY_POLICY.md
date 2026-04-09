# Safety Policy

## Command classes

- Emergency stop: independent safety action
- Stop task: task-level interruption
- Reset fault: recovery action
- Home: controlled recovery / positioning action
- Jog / Servo / Gripper: maintenance actions

## Mandatory gates

- `startTask` requires readiness all green and operator role
- `jogJoint`, `servoCartesian`, `gripper` require maintainer role and manual/maintenance controller mode
- `activateCalibrationVersion` requires maintainer role
- readiness loss can force HMI into read-only degraded state
