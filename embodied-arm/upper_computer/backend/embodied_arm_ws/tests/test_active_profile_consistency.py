from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.check_active_profile_consistency import DEPRECATED_PACKAGES, EXPERIMENTAL_PACKAGES, _parse_launch_packages, validate_active_profile


def test_active_profile_covers_runtime_core_and_supervision_only() -> None:
    assert validate_active_profile() == []


def test_active_profile_quarantine_manifest_matches_pytest_ignores() -> None:
    issues = [issue for issue in validate_active_profile() if 'quarantine' in issue or 'ignores' in issue]
    assert issues == []



def test_arm_vision_is_consistently_treated_as_compatibility_only() -> None:
    _, _, compat, experimental = _parse_launch_packages()
    assert 'arm_vision' in compat
    assert 'arm_vision' in DEPRECATED_PACKAGES
    assert 'arm_vision' not in experimental



def test_taxonomy_constants_are_derived_from_launch_factory() -> None:
    _, _, compat, experimental = _parse_launch_packages()
    assert DEPRECATED_PACKAGES == compat
    assert EXPERIMENTAL_PACKAGES == experimental
