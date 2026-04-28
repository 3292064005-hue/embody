from arm_scene_manager import SceneManagerNode


def test_scene_manager_tracks_target_and_attachments() -> None:
    node = SceneManagerNode()
    snapshot = node.sync_scene({'target': {'target_id': 't1', 'target_type': 'cube', 'table_x': 0.1, 'table_y': 0.2, 'confidence': 0.9}})
    assert snapshot['sceneAvailable'] is True
    assert snapshot['targetCollisionObject']['id'] == 't1'
    assert snapshot['objectCount'] >= 3

    attachment = node.attach_target('t1', link_name='tool0')
    assert attachment['targetId'] == 't1'
    assert node.current_scene()['attachments'][0]['targetId'] == 't1'

    detached = node.detach_target('t1')
    assert detached['detached'] is True
    assert node.current_scene()['attachments'] == []
