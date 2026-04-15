from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Iterable, Iterator
import json

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / 'embodied-arm-fullstack-release.zip'
MANIFEST_OUTPUT = ROOT / 'artifacts' / 'release_manifest.json'
EXCLUDE_PREFIXES = {
    Path('.git'),
    Path('artifacts'),
    Path('gateway_data'),
    Path('frontend/node_modules'),
    Path('frontend/dist'),
    Path('backend/embodied_arm_ws/build'),
    Path('backend/embodied_arm_ws/install'),
    Path('backend/embodied_arm_ws/log'),
    Path('backend/embodied_arm_ws/.active_overlay'),
    Path('backend/embodied_arm_ws/src/arm_hmi'),
    Path('backend/embodied_arm_ws/src/arm_task_manager'),
    Path('backend/embodied_arm_ws/src/arm_motion_bridge'),
    Path('backend/embodied_arm_ws/src/arm_vision'),
    Path('backend/embodied_arm_ws/src/experimental'),
    Path('third_party'),
}
EXCLUDE_PARTS = {'__pycache__', '.pytest_cache', '.vite'}
EXCLUDE_FILES = {'.coverage', 'DELIVERY_REPORT.md'}
EXCLUDE_SUFFIXES = {'.pyc', '.pyo', '.tsbuildinfo', '.zip'}


def _is_relative_to(path: Path, prefix: Path) -> bool:
    try:
        path.relative_to(prefix)
        return True
    except ValueError:
        return False


def should_skip(path: Path) -> bool:
    return (
        any(_is_relative_to(path, prefix) for prefix in EXCLUDE_PREFIXES)
        or any(part in EXCLUDE_PARTS for part in path.parts)
        or path.name in EXCLUDE_FILES
        or path.suffix in EXCLUDE_SUFFIXES
    )


def iter_release_files(root: Path = ROOT) -> Iterator[Path]:
    for file_path in sorted(root.rglob('*')):
        if file_path.is_dir():
            continue
        relative = file_path.relative_to(root)
        if should_skip(relative):
            continue
        yield file_path


def build_release_archive(output: Path = OUTPUT, root: Path = ROOT, files: Iterable[Path] | None = None) -> Path:
    selected = list(files) if files is not None else list(iter_release_files(root))
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file_path in selected:
            archive.write(file_path, file_path.relative_to(root).as_posix())
    return output


def write_release_manifest(files: Iterable[Path], output: Path = MANIFEST_OUTPUT, root: Path = ROOT) -> Path:
    """Persist the deterministic release manifest for the packaged source tree.

    Args:
        files: Iterable of absolute source paths selected for packaging.
        output: Manifest output path.
        root: Repository root used to compute relative archive entries.

    Returns:
        The manifest path written to disk.

    Raises:
        OSError: Propagates filesystem write failures.

    Boundary behavior:
        Parent directories are created automatically before the manifest is written.
    """
    selected = [path.relative_to(root).as_posix() for path in files]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'fileCount': len(selected), 'files': selected}, indent=2), encoding='utf-8')
    return output


def main() -> None:
    files = list(iter_release_files())
    output = build_release_archive(files=files)
    manifest = write_release_manifest(files)
    print(f'created: {output}')
    print(f'manifest: {manifest}')


if __name__ == '__main__':
    main()
