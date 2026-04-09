from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'scripts' / 'sync_interface_mirror.py'


def test_interface_mirror_check_gate_passes_for_current_repo() -> None:
    completed = subprocess.run([sys.executable, str(SCRIPT), '--check'], cwd=str(ROOT), capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert 'mirror check passed' in completed.stdout
