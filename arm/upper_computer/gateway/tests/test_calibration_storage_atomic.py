from __future__ import annotations

import json
from pathlib import Path

from gateway.storage import CalibrationStorage


def test_calibration_storage_writes_pointer_and_journal_atomically(tmp_path: Path):
    storage = CalibrationStorage(tmp_path / 'gateway_data', tmp_path / 'default_calibration.yaml')
    versions = storage.save_profile(
        {
            'profileName': 'lab-a',
            'roi': {'x': 0, 'y': 0, 'width': 640, 'height': 480},
            'tableScaleMmPerPixel': 1.0,
            'offsets': {'x': 0.1, 'y': -0.1, 'z': 0.0},
            'updatedAt': '2026-04-01T00:00:00Z',
        },
        profile_id='cal-1',
    )
    assert versions[0]['id'] == 'cal-1'
    pointer = json.loads((tmp_path / 'gateway_data' / 'calibration_active_pointer.json').read_text(encoding='utf-8'))
    assert pointer['activeProfileId'] == 'cal-1'
    assert pointer['runtimeState'] == 'pending_runtime_apply'
    journal = (tmp_path / 'gateway_data' / 'calibration_activation_journal.jsonl').read_text(encoding='utf-8').strip().splitlines()
    assert journal
    assert 'save_profile' in journal[-1]

    updated_versions = storage.mark_runtime_applied('cal-1', True, 'runtime accepted')
    assert updated_versions[0]['runtimeApplied'] is True
    assert updated_versions[0]['runtimeState'] == 'active'
