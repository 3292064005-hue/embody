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


def test_package_split_release_check_ignores_workspace_repo_validation_summaries(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    manifest = repo_root / 'artifacts' / 'split_release_manifest.json'
    backup = manifest.read_bytes() if manifest.exists() else None
    summary_paths = [
        repo_root / 'upper_computer' / 'artifacts' / 'repository_validation' / 'fast' / 'verification_summary.json',
        repo_root / 'upper_computer' / 'artifacts' / 'repository_validation' / 'repo' / 'verification_summary.json',
        repo_root / 'upper_computer' / 'artifacts' / 'repository_validation' / 'release' / 'verification_summary.json',
    ]
    backups: dict[Path, bytes | None] = {}
    try:
        for path in summary_paths:
            backups[path] = path.read_bytes() if path.exists() else None
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"profile":"repo","overallStatus":"passed","requiredSteps":[],"stepStatuses":{}}\n', encoding='utf-8')
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
        for path, data in backups.items():
            if data is None:
                path.unlink(missing_ok=True)
                parent = path.parent
                while parent != repo_root and parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
            else:
                path.write_bytes(data)
        if backup is not None:
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_bytes(backup)
