from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_package_split_release_check_succeeds_without_manifest_file(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    manifest = repo_root / 'artifacts' / 'split_release_manifest.json'
    backup = None
    if manifest.exists():
        backup = manifest.read_bytes()
        manifest.unlink()
    try:
        result = subprocess.run(
            [sys.executable, 'scripts/package_split_release.py', '--check'],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        assert 'split release manifest check passed' in result.stdout.lower()
    finally:
        if backup is not None:
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_bytes(backup)
