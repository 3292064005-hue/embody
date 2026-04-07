from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.check_active_profile_consistency import validate_active_profile


def test_active_profile_covers_runtime_core_and_supervision_only() -> None:
    assert validate_active_profile() == []
