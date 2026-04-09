class FrameIds:
    WORLD = 'world'
    TABLE = 'table'
    BASE_LINK = 'base_link'
    SHOULDER_LINK = 'shoulder_link'
    ELBOW_LINK = 'elbow_link'
    WRIST_LINK = 'wrist_link'
    TOOL0 = 'tool0'
    GRIPPER_TCP = 'gripper_tcp'
    CAMERA_LINK = 'camera_link'
    CAMERA_OPTICAL_FRAME = 'camera_optical_frame'
    @staticmethod
    def target_frame(target_id: str) -> str:
        return f'target_frame_{target_id}'
