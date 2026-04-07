from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'backend' / 'embodied_arm_ws' / 'src'
ARM_INTERFACES = ROOT / 'arm_interfaces'
ARM_MSGS = ROOT / 'arm_msgs'
SUBDIRS = ('msg', 'srv', 'action')


def main() -> int:
    for subdir in SUBDIRS:
        source_dir = ARM_INTERFACES / subdir
        target_dir = ARM_MSGS / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        for path in target_dir.glob('*'):
            if path.is_file():
                path.unlink()
        for source in sorted(source_dir.glob('*')):
            if source.is_file():
                shutil.copy2(source, target_dir / source.name)
    print('arm_interfaces mirrored into arm_msgs')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
