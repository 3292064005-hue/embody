from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / 'artifacts' / 'target_env_report.json'
DEFAULT_ROS_SETUP = '/opt/ros/humble/setup.bash'


def _read_os_release() -> dict[str, str]:
    path = Path('/etc/os-release')
    if not path.exists():
        return {}
    facts: dict[str, str] = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        facts[key] = value.strip().strip('"')
    return facts


def _command_version(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except Exception:
        return None
    output = (completed.stdout or completed.stderr).strip()
    return output.splitlines()[0] if output else None


def collect_facts(*, ros_setup: str = DEFAULT_ROS_SETUP, workspace_dir: Path | None = None) -> dict[str, Any]:
    workspace = workspace_dir or (ROOT / 'backend' / 'embodied_arm_ws')
    os_release = _read_os_release()
    return {
        'platformSystem': platform.system(),
        'platformRelease': platform.release(),
        'osRelease': os_release,
        'pythonVersion': platform.python_version(),
        'nodeVersion': _command_version(['node', '--version']),
        'npmVersion': _command_version(['npm', '--version']),
        'rosSetupPath': ros_setup,
        'rosSetupExists': Path(ros_setup).is_file(),
        'colconPath': shutil.which('colcon'),
        'ros2Path': shutil.which('ros2'),
        'workspaceDir': str(workspace),
        'workspaceExists': workspace.is_dir(),
        'recommendedReleaseTier': 'runtime-ready' if workspace.is_dir() else 'candidate-only',
    }


def _check(name: str, passed: bool, expected: str, actual: Any) -> dict[str, Any]:
    return {
        'name': name,
        'passed': bool(passed),
        'expected': expected,
        'actual': actual,
    }


def validate_facts(facts: dict[str, Any]) -> dict[str, Any]:
    os_release = facts.get('osRelease') or {}
    checks = [
        _check('os.platform', facts.get('platformSystem') == 'Linux', 'Linux', facts.get('platformSystem')),
        _check('os.ubuntu', os_release.get('ID') == 'ubuntu', 'ubuntu', os_release.get('ID')),
        _check('os.version', os_release.get('VERSION_ID') == '22.04', '22.04', os_release.get('VERSION_ID')),
        _check('python.version', str(facts.get('pythonVersion', '')).startswith('3.10.'), '3.10.x', facts.get('pythonVersion')),
        _check('node.version', str(facts.get('nodeVersion', '')).startswith('v22.'), 'v22.x', facts.get('nodeVersion')),
        _check('npm.version', str(facts.get('npmVersion', '')).startswith('10.9.'), '10.9.x', facts.get('npmVersion')),
        _check('ros.setup', bool(facts.get('rosSetupExists')), 'existing ROS setup script', facts.get('rosSetupPath')),
        _check('tool.colcon', bool(facts.get('colconPath')), 'colcon on PATH', facts.get('colconPath')),
        _check('tool.ros2', bool(facts.get('ros2Path')), 'ros2 CLI on PATH', facts.get('ros2Path')),
        _check('workspace.exists', bool(facts.get('workspaceExists')), 'backend/embodied_arm_ws present', facts.get('workspaceDir')),
    ]
    return {
        'ok': all(item['passed'] for item in checks),
        'checks': checks,
        'facts': facts,
    }


def write_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate the target Ubuntu 22.04 + ROS2 Humble environment lane.')
    parser.add_argument('--output', type=Path, default=DEFAULT_REPORT, help='Path to write the JSON report.')
    parser.add_argument('--ros-setup', default=os.environ.get('ROS_SETUP', DEFAULT_ROS_SETUP), help='ROS setup script path.')
    parser.add_argument('--strict', action='store_true', help='Exit with code 1 if any check fails.')
    args = parser.parse_args(argv)

    report = validate_facts(collect_facts(ros_setup=args.ros_setup))
    write_report(report, args.output)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.strict and not report['ok']:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
