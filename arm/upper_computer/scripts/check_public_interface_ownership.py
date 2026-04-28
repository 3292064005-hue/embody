from __future__ import annotations

from pathlib import Path

from check_active_profile_consistency import load_launch_package_taxonomy

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend' / 'embodied_arm_ws' / 'src'
SERVICE_NAMES = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_common' / 'arm_common' / 'service_names.py'
ACTION_NAMES = ROOT / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_common' / 'arm_common' / 'action_names.py'


def _extract_public_endpoints(path: Path, *, marker: str) -> set[str]:
    payload: set[str] = set()
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if marker not in line or '=' not in line:
            continue
        value = line.split('=', 1)[1].strip().strip('"').strip("'")
        if value.startswith('/arm/') and '/compat/' not in value:
            payload.add(value)
    return payload


def validate_public_interface_ownership() -> list[str]:
    _, _, deprecated, experimental = load_launch_package_taxonomy()
    disallowed_packages = deprecated | experimental
    canonical_services = _extract_public_endpoints(SERVICE_NAMES, marker='/arm/')
    canonical_actions = _extract_public_endpoints(ACTION_NAMES, marker='/arm/')
    issues: list[str] = []
    for package_name in sorted(disallowed_packages):
        package_root = BACKEND / package_name
        if not package_root.exists():
            continue
        for path in sorted(package_root.rglob('*.py')):
            if '__pycache__' in path.parts:
                continue
            text = path.read_text(encoding='utf-8')
            for endpoint in sorted(canonical_services | canonical_actions):
                if endpoint in text:
                    issues.append(
                        f'deprecated/experimental package {package_name} still exposes canonical public endpoint {endpoint}: '
                        f'{path.relative_to(ROOT)}'
                    )
    return issues


def main() -> int:
    issues = validate_public_interface_ownership()
    if issues:
        print('PUBLIC INTERFACE OWNERSHIP CHECK FAILED')
        for issue in issues:
            print(f'- {issue}')
        return 1
    print('PUBLIC INTERFACE OWNERSHIP CHECK PASSED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
