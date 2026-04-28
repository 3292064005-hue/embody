from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SECTION_DIR = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config' / 'runtime_authority_sections'


def test_runtime_authority_section_projections_are_in_sync() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'sync_runtime_authority.py'), '--check'],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_runtime_authority_section_projection_payloads_exist() -> None:
    expected = {
        'product_lines.yaml': 'product_lines',
        'command_planes.yaml': 'command_planes',
        'capability_registry.yaml': 'capability_registry',
        'task_catalog_contract.yaml': 'task_catalog_contract',
        'runtime_governance.yaml': 'runtime_governance',
    }
    for filename, root_key in expected.items():
        payload = yaml.safe_load((SECTION_DIR / filename).read_text(encoding='utf-8')) or {}
        assert root_key in payload



def test_runtime_implementer_docs_gate_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'check_runtime_implementer_docs.py')],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
