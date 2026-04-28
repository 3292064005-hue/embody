from __future__ import annotations

"""Build and validate the top-level split-release source package.

The source archive keeps the repository's three delivery surfaces together:
``upper_computer/``, ``esp32s3_platformio/`` and ``stm32f103c8_platformio/``.
Only deterministic evidence artifacts are packaged; per-worktree validation logs,
cache directories and generated binaries are excluded.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'embodied-arm-split-release.zip'
MANIFEST_OUTPUT = ROOT / 'artifacts' / 'split_release_manifest.json'

EXCLUDE_PREFIXES = {
    Path('.git'),
    Path('artifacts/repository_validation'),
    Path('upper_computer/artifacts/repository_validation'),
    Path('upper_computer/.git'),
    Path('upper_computer/gateway_data'),
    Path('upper_computer/frontend/node_modules'),
    Path('upper_computer/frontend/dist'),
    Path('upper_computer/backend/embodied_arm_ws/build'),
    Path('upper_computer/backend/embodied_arm_ws/install'),
    Path('upper_computer/backend/embodied_arm_ws/log'),
    Path('upper_computer/backend/embodied_arm_ws/.active_overlay'),
    Path('upper_computer/backend/embodied_arm_ws/src/arm_hmi'),
    Path('upper_computer/backend/embodied_arm_ws/src/arm_task_manager'),
    Path('upper_computer/backend/embodied_arm_ws/src/arm_motion_bridge'),
    Path('upper_computer/backend/embodied_arm_ws/src/arm_vision'),
    Path('upper_computer/backend/embodied_arm_ws/src/experimental'),
    Path('upper_computer/third_party'),
}
EXCLUDE_PARTS = {'__pycache__', '.pytest_cache', '.vite'}
EXCLUDE_FILES = {'.coverage', 'DELIVERY_REPORT.md', 'runtime_baseline_repo_sample.json'}
EXCLUDE_SUFFIXES = {'.pyc', '.pyo', '.tsbuildinfo', '.zip'}
INCLUDED_ARTIFACTS = {
    Path('.gitignore'),
    Path('scripts/package_split_release.py'),
    Path('artifacts/split_release_manifest.json'),
    Path('upper_computer/artifacts/release_gates/frontend_validation_ledger.json'),
    Path('upper_computer/artifacts/release_gates/release_evidence.json'),
    Path('upper_computer/artifacts/release_gates/runtime_baseline_report.json'),
    Path('upper_computer/artifacts/release_gates/validated_live_hil_gate.json'),
    Path('upper_computer/artifacts/release_gates/validated_live_release_checklist_gate.json'),
    Path('upper_computer/artifacts/target_env_report.json'),
    Path('upper_computer/artifacts/repository_validation/repo/verification_summary.json'),
}

INCLUDED_ARTIFACT_PREFIXES = {
    Path('upper_computer/artifacts/release_gates/frontend_validation_artifacts'),
    Path('upper_computer/artifacts/repository_validation/repo'),
}
REQUIRED_TOP_LEVEL_PREFIXES = {
    Path('upper_computer'),
    Path('esp32s3_platformio'),
    Path('stm32f103c8_platformio'),
}
ROOT_INCLUDED_FILES = {Path('.gitignore'), Path('scripts/package_split_release.py'), Path('artifacts/split_release_manifest.json')}


_INCLUDED_ARTIFACT_STRS = {path.as_posix() for path in INCLUDED_ARTIFACTS}
_INCLUDED_ARTIFACT_PREFIX_STRS = tuple(path.as_posix() for path in INCLUDED_ARTIFACT_PREFIXES)
_EXCLUDE_PREFIX_STRS = tuple(path.as_posix() for path in EXCLUDE_PREFIXES)
_REQUIRED_TOP_LEVEL_PREFIX_STRS = tuple(path.as_posix() for path in REQUIRED_TOP_LEVEL_PREFIXES)
_ROOT_INCLUDED_FILE_STRS = {path.as_posix() for path in ROOT_INCLUDED_FILES}


def _is_relative_to_str(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(f'{prefix}/')


def _has_included_descendant_str(path: str) -> bool:
    return (
        any(_is_relative_to_str(item, path) for item in _INCLUDED_ARTIFACT_STRS)
        or any(_is_relative_to_str(prefix, path) for prefix in _INCLUDED_ARTIFACT_PREFIX_STRS)
    )


def _should_prune_dir_str(path: str) -> bool:
    parts = path.split('/') if path else []
    if any(part in EXCLUDE_PARTS for part in parts):
        return True
    if any(_is_relative_to_str(path, prefix) for prefix in _EXCLUDE_PREFIX_STRS):
        return not _has_included_descendant_str(path)
    return False


def _should_skip_str(path: str) -> bool:
    parts = path.split('/') if path else []
    name = parts[-1] if parts else ''
    suffix = Path(name).suffix
    if path in _INCLUDED_ARTIFACT_STRS or any(_is_relative_to_str(path, prefix) for prefix in _INCLUDED_ARTIFACT_PREFIX_STRS):
        return False
    return (
        any(_is_relative_to_str(path, prefix) for prefix in _EXCLUDE_PREFIX_STRS)
        or any(part in EXCLUDE_PARTS for part in parts)
        or name in EXCLUDE_FILES
        or suffix in EXCLUDE_SUFFIXES
    )


def _is_in_required_top_level(path: str) -> bool:
    return path in _ROOT_INCLUDED_FILE_STRS or any(_is_relative_to_str(path, prefix) for prefix in _REQUIRED_TOP_LEVEL_PREFIX_STRS)


def _is_relative_to(path: Path, prefix: Path) -> bool:
    """Return whether `path` is equal to or below `prefix` without exceptions.

    Args:
        path: Repository-relative candidate path.
        prefix: Repository-relative prefix.

    Returns:
        True when `path` has `prefix` as a path-component prefix.
    """
    path_parts = path.parts
    prefix_parts = prefix.parts
    return len(path_parts) >= len(prefix_parts) and path_parts[: len(prefix_parts)] == prefix_parts


def _has_included_descendant(path: Path) -> bool:
    """Return whether an otherwise excluded directory contains allowlisted outputs.

    Args:
        path: Repository-relative directory path.

    Returns:
        True when package selection must continue traversing the directory to
        reach explicitly included artifacts.
    """
    return (
        any(_is_relative_to(item, path) for item in INCLUDED_ARTIFACTS)
        or any(_is_relative_to(prefix, path) for prefix in INCLUDED_ARTIFACT_PREFIXES)
    )


def _should_prune_dir(path: Path) -> bool:
    """Return whether directory traversal can be safely skipped.

    Args:
        path: Repository-relative directory path.

    Returns:
        True when no allowlisted descendant can be selected from this directory.

    Boundary behavior:
        Directory pruning is an optimization only; file-level `should_skip()`
        remains authoritative. Allowlisted artifact subtrees under normally
        excluded parents are preserved.
    """
    if any(part in EXCLUDE_PARTS for part in path.parts):
        return True
    if any(_is_relative_to(path, prefix) for prefix in EXCLUDE_PREFIXES):
        return not _has_included_descendant(path)
    return False


def should_skip(path: Path) -> bool:
    if path in INCLUDED_ARTIFACTS or any(_is_relative_to(path, prefix) for prefix in INCLUDED_ARTIFACT_PREFIXES):
        return False
    return (
        any(_is_relative_to(path, prefix) for prefix in EXCLUDE_PREFIXES)
        or any(part in EXCLUDE_PARTS for part in path.parts)
        or path.name in EXCLUDE_FILES
        or path.suffix in EXCLUDE_SUFFIXES
    )


def iter_release_files(root: Path = ROOT) -> Iterator[Path]:
    """Yield deterministic top-level split-release files.

    Args:
        root: Repository root to scan.

    Returns:
        An iterator of regular files accepted by the split-release filter. The
        traversal order is stable and independent of filesystem glob behavior.

    Boundary behavior:
        Excluded directories are pruned unless they contain allowlisted
        artifact paths. File-level filtering remains the authoritative gate.
    """
    root = root if root.is_absolute() else root.absolute()
    root_text = os.fspath(root)
    for dirpath, dirnames, filenames in os.walk(root_text):
        dirnames[:] = [
            dirname
            for dirname in sorted(dirnames)
            if not _should_prune_dir_str(os.path.relpath(os.path.join(dirpath, dirname), root_text).replace(os.sep, '/'))
        ]
        for filename in sorted(filenames):
            file_path = os.path.join(dirpath, filename)
            relative = os.path.relpath(file_path, root_text).replace(os.sep, '/')
            if _should_skip_str(relative):
                continue
            if not _is_in_required_top_level(relative):
                continue
            yield Path(file_path)


def _selected_relative_files(root: Path = ROOT) -> list[str]:
    return [path.relative_to(root).as_posix() for path in iter_release_files(root)]


def _selected_release_files_with_manifest(
    root: Path = ROOT,
    *,
    manifest_path: Path = MANIFEST_OUTPUT,
    files: Iterable[Path] | None = None,
) -> list[Path]:
    """Return the deterministic split-release selection including its manifest.

    Args:
        root: Top-level repository root used for path normalization.
        manifest_path: Split manifest path that must be represented as a
            self-reference.
        files: Optional base selection. When omitted, the package selector is
            scanned.

    Returns:
        A sorted, de-duplicated list whose paths match both the manifest payload
        and the archive members. The manifest is included even on a clean
        first-run before it exists on disk.

    Raises:
        ValueError: If the manifest path is outside the repository root.

    Boundary behavior:
        Only the manifest path is allowed to be missing during manifest creation;
        all other selected package members must exist and hash as regular files.
    """
    root_absolute = root if root.is_absolute() else root.absolute()
    manifest_absolute = manifest_path if manifest_path.is_absolute() else root_absolute / manifest_path
    try:
        manifest_relative = manifest_absolute.relative_to(root_absolute)
    except ValueError as exc:
        raise ValueError(f'split release manifest must be inside package root: {manifest_absolute}') from exc
    selected = list(files) if files is not None else list(iter_release_files(root_absolute))
    by_relative: dict[str, Path] = {}
    for path in selected:
        absolute = path if path.is_absolute() else root_absolute / path
        by_relative[absolute.relative_to(root_absolute).as_posix()] = absolute
    by_relative[manifest_relative.as_posix()] = manifest_absolute
    return [by_relative[key] for key in sorted(by_relative)]


def _file_provenance(path: Path, root: Path = ROOT, *, output_path: Path | None = None) -> dict[str, object]:
    """Return stable file-level provenance for one top-level package member.

    Args:
        path: Absolute or root-relative file path selected for the split release.
        root: Repository root used to render the canonical package path.
        output_path: Manifest being written, used to mark self-referential records.

    Returns:
        A JSON-safe record containing `path`, `sizeBytes`, `sha256`, and
        `provenanceStatus` for the exact bytes that enter the archive.

    Raises:
        FileNotFoundError: If a non-self-referential selected path does not exist.
        IsADirectoryError: If a non-self-referential selected path is a directory.

    Boundary behavior:
        Hashing uses raw bytes and follows the same Path resolution behavior as
        zipfile packaging. Directories are never represented as synthetic file
        records. The manifest output itself is marked
        `self_referential_manifest` because embedding its final digest would
        change the bytes being hashed.
    """
    root_absolute = root if root.is_absolute() else root.absolute()
    absolute = path if path.is_absolute() else root_absolute / path
    output_absolute = None if output_path is None else (output_path if output_path.is_absolute() else root_absolute / output_path)
    relative = absolute.relative_to(root_absolute).as_posix()
    if output_absolute is not None and absolute == output_absolute:
        return {
            'path': relative,
            'sizeBytes': None,
            'sha256': None,
            'provenanceStatus': 'self_referential_manifest',
        }
    stat = absolute.stat()
    if not absolute.is_file():
        raise IsADirectoryError(str(absolute))
    return {
        'path': relative,
        'sizeBytes': stat.st_size,
        'sha256': hashlib.sha256(absolute.read_bytes()).hexdigest(),
        'provenanceStatus': 'recorded',
    }

def _file_provenance_records(files: Iterable[Path], root: Path = ROOT, *, output_path: Path | None = None) -> list[dict[str, object]]:
    """Build ordered split-release provenance records.

    Args:
        files: Files returned by the deterministic split package selector.
        root: Repository root for path normalization and hashing.
        output_path: Manifest being written, used to mark the self-reference.

    Returns:
        Records ordered one-to-one with the compatibility `files` list.

    Raises:
        FileNotFoundError, IsADirectoryError: Propagated so stale selections fail
        closed instead of producing an incomplete manifest.
    """
    return [_file_provenance(path, root=root, output_path=output_path) for path in files]


def write_release_manifest(files: Iterable[Path], output: Path = MANIFEST_OUTPUT, root: Path = ROOT) -> Path:
    """Persist the deterministic top-level split release manifest.

    Args:
        files: Deterministically selected split package files.
        output: Manifest JSON destination.
        root: Repository root used for relative paths and file hashing.

    Returns:
        The manifest path written to disk.

    Raises:
        FileNotFoundError, IsADirectoryError: If any selected input cannot be
        hashed as a regular file.

    Boundary behavior:
        The legacy `files` list is retained for compatibility, and the new
        `fileProvenance` list records one ordered record per packaged member.
        Regular files carry byte size and SHA-256; the manifest output itself is
        marked as a self-reference instead of carrying a stale digest.
    """
    selected_files = _selected_release_files_with_manifest(root, manifest_path=output, files=files)
    selected = [path.relative_to(root).as_posix() for path in selected_files]
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'schemaVersion': 2,
        'generatedBy': 'scripts/package_split_release.py',
        'fileCount': len(selected),
        'files': selected,
        'fileProvenance': _file_provenance_records(selected_files, root=root, output_path=output),
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return output


def build_release_archive(output: Path = OUTPUT, root: Path = ROOT, files: Iterable[Path] | None = None) -> Path:
    selected = list(files) if files is not None else list(iter_release_files(root))
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file_path in selected:
            archive.write(file_path, file_path.relative_to(root).as_posix())
    return output


def _validate_manifest_provenance(payload: dict, expected_files: list[Path], root: Path, manifest_path: Path) -> list[str]:
    """Validate split-release path, size and SHA-256 provenance.

    Args:
        payload: Parsed manifest JSON object.
        expected_files: Current deterministic package selection.
        root: Repository root used to resolve relative paths.
        manifest_path: Manifest path used to mark self-referential provenance.

    Returns:
        Audit issues. Empty means the manifest matches the selected package
        members byte-for-byte.

    Boundary behavior:
        Manifests that only contain the legacy `files` list are treated as stale;
        callers receive an explicit provenance issue instead of a false pass.
    """
    issues: list[str] = []
    expected_records = _file_provenance_records(expected_files, root=root, output_path=manifest_path)
    provenance = payload.get('fileProvenance')
    if not isinstance(provenance, list):
        return ['split release manifest missing fileProvenance records']
    actual_records = [item for item in provenance if isinstance(item, dict)]
    if len(actual_records) != len(provenance):
        issues.append('split release manifest fileProvenance contains non-object entries')
    normalized_actual = [
        {
            'path': str(item.get('path', '') or ''),
            'sizeBytes': item.get('sizeBytes'),
            'sha256': item.get('sha256') if item.get('sha256') is None else str(item.get('sha256', '') or ''),
            'provenanceStatus': str(item.get('provenanceStatus', '') or ''),
        }
        for item in actual_records
    ]
    if normalized_actual != expected_records:
        issues.append('split release manifest fileProvenance drift detected')
    return issues


def check_manifest(manifest_path: Path = MANIFEST_OUTPUT, root: Path = ROOT) -> list[str]:
    """Validate the split release manifest against current package selection.

    Args:
        manifest_path: Manifest JSON path.
        root: Repository root to scan.

    Returns:
        Audit issues. Missing manifest fails closed because release packaging and
        final audit must verify an existing provenance ledger.
    """
    issues: list[str] = []
    expected_files = _selected_release_files_with_manifest(root, manifest_path=manifest_path)
    expected = [path.relative_to(root).as_posix() for path in expected_files]
    if not manifest_path.exists():
        return [f'split release manifest missing: {manifest_path.relative_to(root).as_posix()}']
    try:
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception as exc:
        return [f'failed to parse split release manifest: {exc}']
    if not isinstance(payload, dict):
        return ['split release manifest must be a JSON object']
    if payload.get('schemaVersion') != 2:
        issues.append('split release manifest schemaVersion must be 2')
    if payload.get('generatedBy') != 'scripts/package_split_release.py':
        issues.append('split release manifest generatedBy drift detected')
    if payload.get('fileCount') != len(expected):
        issues.append('split release manifest fileCount drift detected')
    files = payload.get('files', [])
    actual = [str(item) for item in files if isinstance(item, str)] if isinstance(files, list) else []
    if not isinstance(files, list) or len(actual) != len(files):
        issues.append('split release manifest files must be a list of strings')
    if actual != expected:
        issues.append('split release manifest drift detected')
    issues.extend(_validate_manifest_provenance(payload, expected_files, root, manifest_path))
    for required in INCLUDED_ARTIFACTS:
        if not (root / required).exists():
            issues.append(f'required release artifact missing from split package selection: {required.as_posix()}')
        elif required.as_posix() not in expected:
            issues.append(f'required release artifact missing from split package selection: {required.as_posix()}')
    return issues

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Package or validate the split source release archive.')
    parser.add_argument('--check', action='store_true', help='Validate the deterministic split release manifest without writing the archive.')
    args = parser.parse_args(argv)
    if args.check:
        issues = check_manifest()
        if issues:
            raise SystemExit('\n'.join(issues))
        print('split release manifest check passed')
        return 0
    files = _selected_release_files_with_manifest()
    manifest = write_release_manifest(files)
    archive = build_release_archive(files=files)
    print(f'created: {archive}')
    print(f'manifest: {manifest}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
