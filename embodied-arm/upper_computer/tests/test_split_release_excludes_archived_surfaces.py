from __future__ import annotations

from pathlib import Path
import importlib.util


def test_split_release_manifest_excludes_archived_runtime_surfaces() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / 'scripts' / 'package_split_release.py'
    spec = importlib.util.spec_from_file_location('package_split_release', script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    selected = {str(path.relative_to(repo_root)) for path in module.iter_release_files()}
    assert 'upper_computer/backend/embodied_arm_ws/src/arm_hmi/package.xml' not in selected
    assert 'upper_computer/backend/embodied_arm_ws/src/arm_task_manager/package.xml' not in selected
    assert 'upper_computer/backend/embodied_arm_ws/src/arm_motion_bridge/package.xml' not in selected
    assert 'upper_computer/backend/embodied_arm_ws/src/arm_vision/package.xml' not in selected
