from __future__ import annotations

import argparse
import filecmp
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'backend' / 'embodied_arm_ws' / 'src'
ARM_INTERFACES = ROOT / 'arm_interfaces'
ARM_MSGS = ROOT / 'arm_msgs'
SUBDIRS = ('msg', 'srv', 'action')


def _sync_subdir(subdir: str) -> None:
    source_dir = ARM_INTERFACES / subdir
    target_dir = ARM_MSGS / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    for path in target_dir.glob('*'):
        if path.is_file():
            path.unlink()
    for source in sorted(source_dir.glob('*')):
        if source.is_file():
            shutil.copy2(source, target_dir / source.name)


def _check_subdir(subdir: str) -> list[str]:
    issues: list[str] = []
    source_dir = ARM_INTERFACES / subdir
    target_dir = ARM_MSGS / subdir
    source_names = sorted(path.name for path in source_dir.glob('*') if path.is_file())
    target_names = sorted(path.name for path in target_dir.glob('*') if path.is_file())
    if source_names != target_names:
        issues.append(f'{subdir} layout drift: {source_names} != {target_names}')
        return issues
    for name in source_names:
        if not filecmp.cmp(source_dir / name, target_dir / name, shallow=False):
            issues.append(f'{subdir}/{name} differs between arm_interfaces and arm_msgs mirror')
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description='Synchronize or verify the arm_interfaces -> arm_msgs compatibility mirror.')
    parser.add_argument('--check', action='store_true', help='Fail if arm_msgs is not an exact mirror of arm_interfaces.')
    args = parser.parse_args()

    if args.check:
        issues: list[str] = []
        for subdir in SUBDIRS:
            issues.extend(_check_subdir(subdir))
        if issues:
            raise SystemExit('\n'.join(issues))
        print('arm_interfaces mirror check passed')
        return 0

    for subdir in SUBDIRS:
        _sync_subdir(subdir)
    print('arm_interfaces mirrored into arm_msgs')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
