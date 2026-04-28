from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

from scripts import verify_repository


def test_verify_repository_intermediate_summary_stays_running_until_last_step() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        artifact_dir = root / 'artifacts' / 'repository_validation' / 'repo'
        required_steps = ['step-a', 'step-b']
        step_statuses = {'step-a': 'passed'}
        with mock.patch.object(verify_repository, 'ROOT_DIR', root):
            verify_repository._write_verification_summary(
                profile='repo',
                artifact_dir=artifact_dir,
                step_statuses=step_statuses,
                overall_status='running',
                required_steps=required_steps,
            )
        payload = json.loads((artifact_dir / 'verification_summary.json').read_text(encoding='utf-8'))
        assert payload['overallStatus'] == 'running'
        assert payload['requiredSteps'] == required_steps
        assert payload['stepStatuses'] == step_statuses
