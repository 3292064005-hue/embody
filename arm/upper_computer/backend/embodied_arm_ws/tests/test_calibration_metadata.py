from arm_backend_common.data_models import CalibrationProfile
from arm_calibration.transform_utils import CalibrationModel


def test_calibration_profile_carries_version_metadata():
    profile = CalibrationProfile(
        version='v2',
        operator='tester',
        camera_serial='cam-01',
        robot_description_hash='robot-hash',
        workspace_id='table-a',
        active=True,
    )
    payload = profile.to_dict()
    assert payload['version'] == 'v2'
    assert payload['operator'] == 'tester'
    assert payload['camera_serial'] == 'cam-01'
    assert payload['robot_description_hash'] == 'robot-hash'
    assert payload['workspace_id'] == 'table-a'
    assert payload['active'] is True


def test_calibration_model_loads_metadata_from_config():
    model = CalibrationModel.from_config({
        'version': 'frozen-1',
        'metadata': {
            'operator': 'alice',
            'camera_serial': 'esp32-cam',
            'robot_description_hash': 'sha256:abc',
            'workspace_id': 'station-1',
            'active': True,
        },
    })
    assert model.profile.version == 'frozen-1'
    assert model.profile.operator == 'alice'
    assert model.profile.camera_serial == 'esp32-cam'
    assert model.profile.robot_description_hash == 'sha256:abc'
    assert model.profile.workspace_id == 'station-1'
    assert model.profile.active is True
