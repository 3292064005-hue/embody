#!/usr/bin/env python3
from __future__ import annotations

"""Materialize an isolated active ROS overlay workspace.

The overlay contains only the active runtime roots plus their in-repository
package dependency closure. Compatibility and experimental packages stay outside
the build surface, so supported build/test entrypoints no longer rely on the
monolithic source tree.
"""

import argparse
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend' / 'embodied_arm_ws'
SRC = BACKEND / 'src'
OVERLAY = BACKEND / '.active_overlay'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_active_profile_consistency import load_launch_package_taxonomy, load_launch_workspace_support_packages

DEPENDENCY_TAGS = (
    'depend',
    'build_depend',
    'build_export_depend',
    'exec_depend',
    'run_depend',
    'test_depend',
    'buildtool_depend',
)


def _workspace_packages() -> dict[str, Path]:
    packages: dict[str, Path] = {}
    for package_xml in SRC.glob('*/package.xml'):
        tree = ET.parse(package_xml)
        name_node = tree.getroot().find('name')
        if name_node is None or not (name_node.text or '').strip():
            continue
        packages[name_node.text.strip()] = package_xml.parent
    return packages


def _package_dependencies(package_dir: Path, known: set[str]) -> set[str]:
    tree = ET.parse(package_dir / 'package.xml')
    deps: set[str] = set()
    for tag in DEPENDENCY_TAGS:
        for node in tree.getroot().findall(tag):
            name = (node.text or '').strip()
            if name in known:
                deps.add(name)
    return deps


def active_workspace_packages() -> tuple[list[str], list[str]]:
    core, supervision, _, _ = load_launch_package_taxonomy()
    support = load_launch_workspace_support_packages()
    roots = sorted(core | supervision)
    package_map = _workspace_packages()
    known = set(package_map)
    closure = set(roots) | set(support)
    queue = list(closure)
    while queue:
        current = queue.pop(0)
        package_dir = package_map.get(current)
        if package_dir is None:
            continue
        for dep in sorted(_package_dependencies(package_dir, known)):
            if dep not in closure:
                closure.add(dep)
                queue.append(dep)
    return roots, sorted(closure)


def materialize_overlay(*, clean: bool = True) -> Path:
    overlay_src = OVERLAY / 'src'
    if clean and OVERLAY.exists():
        shutil.rmtree(OVERLAY)
    overlay_src.mkdir(parents=True, exist_ok=True)
    roots, closure = active_workspace_packages()
    package_map = _workspace_packages()
    for package_name in closure:
        target = package_map.get(package_name)
        if target is None:
            continue
        link_path = overlay_src / package_name
        if link_path.is_symlink() or link_path.exists():
            if link_path.is_dir() and not link_path.is_symlink():
                shutil.rmtree(link_path)
            else:
                link_path.unlink()
        link_path.symlink_to(target.resolve(), target_is_directory=True)
    metadata = OVERLAY / 'overlay_packages.txt'
    metadata.write_text(
        '\n'.join([
            '# active_roots',
            *roots,
            '',
            '# dependency_closure',
            *closure,
            '',
        ]),
        encoding='utf-8',
    )
    return OVERLAY


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--print-root', action='store_true', help='print the overlay root path after materializing it')
    parser.add_argument('--print-packages', action='store_true', help='print the dependency-closure package set')
    parser.add_argument('--delimiter', default=' ', help='delimiter for --print-packages output')
    parser.add_argument('--no-clean', action='store_true', help='preserve an existing overlay and only refresh missing links')
    args = parser.parse_args()

    overlay = materialize_overlay(clean=not args.no_clean)
    _, closure = active_workspace_packages()
    if args.print_packages:
        print(args.delimiter.join(closure))
    else:
        print(str(overlay))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
