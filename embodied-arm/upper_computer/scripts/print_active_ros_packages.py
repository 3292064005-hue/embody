#!/usr/bin/env python3
from __future__ import annotations

"""Print the authoritative active ROS package set for build/test entrypoints.

The active package set is derived from launch-factory package taxonomy instead of
being copied into CI and Makefiles. `--packages-up-to` keeps runtime core and
supervision packages isolated while allowing colcon to pull in their dependency
closure automatically.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_active_profile_consistency import load_launch_package_taxonomy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delimiter', default=' ', help='token delimiter used for output')
    args = parser.parse_args()

    core, supervision, _, _ = load_launch_package_taxonomy()
    packages = sorted(core | supervision)
    print(args.delimiter.join(packages))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
