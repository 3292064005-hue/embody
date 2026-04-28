from arm_camera_driver import CameraDriverNode
from arm_common import TopicNames, ServiceNames, ActionNames, FrameIds
from arm_esp32_gateway import Esp32GatewayNode, VoiceEventClient, BoardHealthParser, StatusNotifier
from arm_grasp_planner import GraspPlannerNode
from arm_perception import PerceptionNode
from arm_scene_manager import SceneManagerNode
from arm_tools import ParameterVerifyTool


def test_new_split_stack_packages_import_and_basic_behaviors():
    assert CameraDriverNode(mock_profile='authoritative_demo').capture_once()['width'] == 640
    assert TopicNames.SYSTEM_STATE == '/arm/system/state'
    assert ServiceNames.START_TASK == '/arm/start_task'
    assert ActionNames.PICK_PLACE_TASK == '/arm/pick_place_task'
    assert FrameIds.target_frame('x') == 'target_frame_x'
    assert PerceptionNode().process({'targets': []}) == []
    scene = SceneManagerNode().sync_scene({'target': {'target_id': 't1', 'target_type': 'cube', 'table_x': 0.1, 'table_y': 0.2}})
    assert scene['sceneAvailable'] is True
    assert scene['targetCollisionObject']['id'] == 't1'
    plan = GraspPlannerNode().plan({'target_id': 't1', 'confidence': 0.9, 'yaw': 0.0}, {'x': 0.2, 'y': 0.1, 'yaw': 0.0})
    assert 'candidate' in plan and 'place' in plan and plan['status'] == 'planned'
    assert ParameterVerifyTool().verify({'a': 1}, ('a', 'b'))['missing'] == ['b']
    assert Esp32GatewayNode.node_name == 'esp32_gateway'
    assert VoiceEventClient().to_event('start')['topic'] == '/arm/voice/events'
    assert BoardHealthParser().parse({'status': 'ok'})['topic'] == '/arm/diagnostics/health'
    assert StatusNotifier().build_notice(online=True, detail='ok', base_url='http://esp32.local')['topic'] == '/arm/readiness/update'
