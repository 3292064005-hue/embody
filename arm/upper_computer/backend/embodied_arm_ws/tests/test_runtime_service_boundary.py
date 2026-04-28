from __future__ import annotations

import pytest

from arm_backend_common import (
    LOCAL_RUNTIME_SERVICE_REGISTRY,
    LocalRuntimeServiceClient,
    RosJsonRuntimeServiceClient,
    RuntimeServiceError,
)
from arm_common import ServiceNames
from arm_grasp_planner import GraspPlannerNode
from arm_motion_planner.providers import GraspRuntimeServiceAdapter, SceneRuntimeServiceAdapter
from arm_scene_manager import SceneManagerNode


def test_runtime_service_adapters_consume_registered_scene_and_grasp_boundaries() -> None:
    scene_node = SceneManagerNode(enable_ros_io=False)
    grasp_node = GraspPlannerNode(enable_ros_io=False)
    try:
        scene = SceneRuntimeServiceAdapter(authoritative=True)
        grasp = GraspRuntimeServiceAdapter(authoritative=True)

        snapshot = scene.sync_scene(
            {
                'target': {
                    'target_id': 't1',
                    'target_type': 'cube',
                    'semantic_label': 'red',
                    'table_x': 0.1,
                    'table_y': 0.2,
                    'yaw': 0.0,
                    'confidence': 0.95,
                }
            }
        )
        assert snapshot['providerMode'] == 'runtime_service'
        assert snapshot['providerAuthoritative'] is True
        assert snapshot['targetCollisionObject']['id'] == 't1'

        plan = grasp.plan(
            {
                'target_id': 't1',
                'target_type': 'cube',
                'semantic_label': 'red',
                'table_x': 0.1,
                'table_y': 0.2,
                'yaw': 0.0,
                'confidence': 0.95,
            },
            {'x': 0.2, 'y': 0.0, 'yaw': 0.0},
            failed_ids=['t1:top_down'],
        )
        assert plan['providerMode'] == 'runtime_service'
        assert plan['providerAuthoritative'] is True
        assert plan['candidate']['candidate_id'] != 't1:top_down'
    finally:
        grasp_node.destroy_node()
        scene_node.destroy_node()


def test_local_runtime_service_client_fails_closed_when_boundary_is_missing() -> None:
    client = LocalRuntimeServiceClient('/arm/internal/missing_runtime_service')
    with pytest.raises(RuntimeServiceError):
        client.call({})


def test_scene_and_grasp_nodes_register_runtime_service_names() -> None:
    scene_node = SceneManagerNode(enable_ros_io=False)
    grasp_node = GraspPlannerNode(enable_ros_io=False)
    try:
        assert LOCAL_RUNTIME_SERVICE_REGISTRY.contains(ServiceNames.RUNTIME_SCENE_SNAPSHOT)
        assert LOCAL_RUNTIME_SERVICE_REGISTRY.contains(ServiceNames.RUNTIME_GRASP_PLAN)
        assert LocalRuntimeServiceClient(ServiceNames.RUNTIME_SCENE_SNAPSHOT).call({'scene': {}})['providerMode'] == 'runtime_service'
        assert LocalRuntimeServiceClient(ServiceNames.RUNTIME_GRASP_PLAN).call(
            {
                'target': {
                    'target_id': 't2',
                    'target_type': 'cube',
                    'semantic_label': 'blue',
                    'table_x': 0.0,
                    'table_y': 0.0,
                    'yaw': 0.0,
                    'confidence': 0.9,
                },
                'place': {'x': 0.2, 'y': 0.0, 'yaw': 0.0},
                'failedIds': [],
            }
        )['providerMode'] == 'runtime_service'
    finally:
        grasp_node.destroy_node()
        scene_node.destroy_node()


def test_destroy_node_unregisters_runtime_service_boundaries() -> None:
    scene_node = SceneManagerNode(enable_ros_io=False)
    grasp_node = GraspPlannerNode(enable_ros_io=False)
    assert LOCAL_RUNTIME_SERVICE_REGISTRY.contains(ServiceNames.RUNTIME_SCENE_SNAPSHOT)
    assert LOCAL_RUNTIME_SERVICE_REGISTRY.contains(ServiceNames.RUNTIME_GRASP_PLAN)

    grasp_node.destroy_node()
    scene_node.destroy_node()

    assert not LOCAL_RUNTIME_SERVICE_REGISTRY.contains(ServiceNames.RUNTIME_SCENE_SNAPSHOT)
    assert not LOCAL_RUNTIME_SERVICE_REGISTRY.contains(ServiceNames.RUNTIME_GRASP_PLAN)


def test_ros_runtime_service_client_without_interface_fails_closed_when_local_fallback_is_disabled() -> None:
    scene_node = SceneManagerNode(enable_ros_io=False)
    try:
        client = RosJsonRuntimeServiceClient(
            node=scene_node,
            service_name=ServiceNames.RUNTIME_SCENE_SNAPSHOT,
            srv_type=object,
            response_json_field='snapshot_json',
            allow_local_fallback=False,
        )
        ready, detail = client.boundary_status()
        assert ready is False
        assert detail == 'runtime_service_interface_unavailable'
        with pytest.raises(RuntimeServiceError, match='runtime_service_interface_unavailable'):
            client.call({'scene': {}})
    finally:
        scene_node.destroy_node()
