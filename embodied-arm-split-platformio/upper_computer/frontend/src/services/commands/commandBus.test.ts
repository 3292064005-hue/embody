import { describe, expect, it, vi, beforeEach } from 'vitest';

const taskActions = {
  startTask: vi.fn().mockResolvedValue(undefined),
  stopTask: vi.fn().mockResolvedValue(undefined)
};
const systemActions = {
  homeRobot: vi.fn().mockResolvedValue(undefined),
  resetFault: vi.fn().mockResolvedValue(undefined),
  emergencyStop: vi.fn().mockResolvedValue(undefined)
};
const robotActions = {
  setControllerMode: vi.fn().mockResolvedValue(undefined),
  setGripper: vi.fn().mockResolvedValue(undefined),
  jogJoint: vi.fn().mockResolvedValue(undefined),
  servo: vi.fn().mockResolvedValue(undefined)
};
const visionActions = {
  saveCalibration: vi.fn().mockResolvedValue(undefined),
  activateProfile: vi.fn().mockResolvedValue(undefined)
};

vi.mock('@/stores/task', () => ({ useTaskStore: () => taskActions }));
vi.mock('@/stores/system', () => ({ useSystemStore: () => systemActions }));
vi.mock('@/stores/robot', () => ({ useRobotStore: () => robotActions }));
vi.mock('@/stores/vision', () => ({ useVisionStore: () => visionActions }));

import { useCommandBus } from './commandBus';

describe('commandBus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('delegates runtime commands to their stores', async () => {
    const bus = useCommandBus();
    await bus.startTask({ taskType: 'pick_place', targetCategory: 'red' });
    await bus.stopTask();
    await bus.home();
    await bus.resetFault();
    await bus.emergencyStop();
    await bus.setControllerMode('maintenance');
    await bus.setGripper(true);
    await bus.jogJoint(0, 1, 2);
    await bus.servoCartesian('x', 0.02);

    expect(taskActions.startTask).toHaveBeenCalledWith({ taskType: 'pick_place', targetCategory: 'red' });
    expect(taskActions.stopTask).toHaveBeenCalledTimes(1);
    expect(systemActions.homeRobot).toHaveBeenCalledTimes(1);
    expect(systemActions.resetFault).toHaveBeenCalledTimes(1);
    expect(systemActions.emergencyStop).toHaveBeenCalledTimes(1);
    expect(robotActions.setControllerMode).toHaveBeenCalledWith('maintenance');
    expect(robotActions.setGripper).toHaveBeenCalledWith(true);
    expect(robotActions.jogJoint).toHaveBeenCalledWith(0, 1, 2);
    expect(robotActions.servo).toHaveBeenCalledWith('x', 0.02);
  });

  it('delegates calibration commands to vision store', async () => {
    const bus = useCommandBus();
    const profile = {
      profileName: 'lab-a',
      roi: { x: 0, y: 0, width: 640, height: 480 },
      tableScaleMmPerPixel: 1,
      offsets: { x: 0, y: 0, z: 0 },
      updatedAt: '2026-03-31T00:00:00Z'
    };
    await bus.saveCalibration(profile);
    await bus.activateCalibrationProfile('cal-1');
    expect(visionActions.saveCalibration).toHaveBeenCalledWith(profile);
    expect(visionActions.activateProfile).toHaveBeenCalledWith('cal-1');
  });
});
