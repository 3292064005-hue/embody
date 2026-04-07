from __future__ import annotations

import json
import zipfile
from pathlib import Path

from scripts.check_target_env import validate_facts, write_report
from scripts.package_release import build_release_archive, iter_release_files


def test_validate_facts_accepts_expected_target_lane(tmp_path: Path):
    facts = {
        'platformSystem': 'Linux',
        'osRelease': {'ID': 'ubuntu', 'VERSION_ID': '22.04'},
        'pythonVersion': '3.10.14',
        'nodeVersion': 'v22.16.0',
        'npmVersion': '10.9.2',
        'rosSetupExists': True,
        'rosSetupPath': '/opt/ros/humble/setup.bash',
        'colconPath': '/usr/bin/colcon',
        'ros2Path': '/usr/bin/ros2',
        'workspaceExists': True,
        'workspaceDir': str(tmp_path / 'backend' / 'embodied_arm_ws'),
    }
    report = validate_facts(facts)
    assert report['ok'] is True
    assert all(item['passed'] for item in report['checks'])


def test_validate_facts_reports_missing_prerequisites(tmp_path: Path):
    facts = {
        'platformSystem': 'Linux',
        'osRelease': {'ID': 'debian', 'VERSION_ID': '12'},
        'pythonVersion': '3.13.5',
        'nodeVersion': 'v20.11.0',
        'npmVersion': '10.8.0',
        'rosSetupExists': False,
        'rosSetupPath': '/missing/setup.bash',
        'colconPath': None,
        'ros2Path': None,
        'workspaceExists': False,
        'workspaceDir': str(tmp_path / 'missing_ws'),
    }
    report = validate_facts(facts)
    assert report['ok'] is False
    failed = {item['name'] for item in report['checks'] if not item['passed']}
    assert {'os.ubuntu', 'os.version', 'python.version', 'node.version', 'npm.version', 'ros.setup', 'tool.colcon', 'tool.ros2', 'workspace.exists'} <= failed


def test_write_report_serializes_validation_output(tmp_path: Path):
    output = tmp_path / 'artifacts' / 'target_env_report.json'
    report = {'ok': False, 'checks': [{'name': 'python.version', 'passed': False}], 'facts': {'pythonVersion': '3.13.5'}}
    write_report(report, output)
    loaded = json.loads(output.read_text(encoding='utf-8'))
    assert loaded == report


def test_release_package_excludes_runtime_state_and_transient_dirs(tmp_path: Path):
    root = tmp_path / 'repo'
    (root / 'gateway_data').mkdir(parents=True)
    (root / 'artifacts' / 'gateway_observability').mkdir(parents=True)
    (root / 'frontend' / 'node_modules').mkdir(parents=True)
    (root / 'backend' / 'embodied_arm_ws' / 'build').mkdir(parents=True)
    (root / 'backend' / 'embodied_arm_ws' / 'install').mkdir(parents=True)
    (root / 'backend' / 'embodied_arm_ws' / 'log').mkdir(parents=True)
    (root / 'frontend' / 'src' / 'components' / 'log').mkdir(parents=True)
    (root / 'app').mkdir(parents=True)
    (root / '.pytest_cache').mkdir(parents=True)
    (root / 'app' / 'keep.txt').write_text('ok', encoding='utf-8')
    (root / 'frontend' / 'src' / 'components' / 'log' / 'keep.vue').write_text('<template />', encoding='utf-8')
    (root / 'gateway_data' / 'active.yaml').write_text('skip', encoding='utf-8')
    (root / 'artifacts' / 'gateway_observability' / 'logs.jsonl').write_text('skip', encoding='utf-8')
    (root / 'frontend' / 'node_modules' / 'dep.js').write_text('skip', encoding='utf-8')
    (root / 'backend' / 'embodied_arm_ws' / 'build' / 'a.txt').write_text('skip', encoding='utf-8')
    (root / 'backend' / 'embodied_arm_ws' / 'log' / 'runtime.log').write_text('skip', encoding='utf-8')
    (root / '.coverage').write_text('skip', encoding='utf-8')

    selected = [path.relative_to(root).as_posix() for path in iter_release_files(root)]
    assert selected == ['app/keep.txt', 'frontend/src/components/log/keep.vue']

    archive_path = tmp_path / 'release.zip'
    build_release_archive(archive_path, root)
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
    assert names == ['app/keep.txt', 'frontend/src/components/log/keep.vue']


def test_ws_contract_doc_matches_bootstrap_versioning():
    text = Path('docs/API_CONTRACT_WS.md').read_text(encoding='utf-8')
    assert '"schemaVersion": "1.1"' in text
    assert '"snapshotVersion": 1' in text
    assert 'bootstrapComplete=true' in text
    assert '"deliveryMode": "snapshot"' in text
    assert '"topicRevision": 7' in text



def test_target_env_bootstrap_script_contains_required_steps():
    text = Path('scripts/bootstrap_target_env_ubuntu2204.sh').read_text(encoding='utf-8')
    assert 'Ubuntu 22.04' in text
    assert 'node_22.x' in text
    assert 'ros-humble-desktop' in text
    assert 'python3-colcon-common-extensions' in text
    assert 'rosdep update' in text


def test_target_env_bootstrap_is_documented():
    readme = Path('README.md').read_text(encoding='utf-8')
    validation = Path('VALIDATION.md').read_text(encoding='utf-8')
    assert 'make target-env-bootstrap' in readme
    assert 'make target-env-bootstrap' in validation



def test_frontend_dependency_bootstrap_uses_local_npmrc():
    text = Path('scripts/ensure_frontend_deps.sh').read_text(encoding='utf-8')
    assert 'NPM_CONFIG_USERCONFIG' in text
    assert '.npmrc' in text
    assert 'NPM_CONFIG_REGISTRY="https://registry.npmjs.org/"' in text
    assert 'unset NODE_AUTH_TOKEN NPM_TOKEN' in text
    assert 'npm ci --userconfig' in text
    assert '--registry "${NPM_CONFIG_REGISTRY}"' in text


def test_docker_target_validation_lane_is_present_and_documented():
    dockerfile = Path('docker/target_env_validation.Dockerfile').read_text(encoding='utf-8')
    helper = Path('scripts/ros_target_validation_in_docker.sh').read_text(encoding='utf-8')
    makefile = Path('Makefile').read_text(encoding='utf-8')
    readme = Path('README.md').read_text(encoding='utf-8')
    validation = Path('VALIDATION.md').read_text(encoding='utf-8')
    assert 'ros:humble-ros-base-jammy' in dockerfile
    assert 'node_22.x' in dockerfile
    assert 'npm install -g npm@10.9.2' in dockerfile
    assert 'docker build' in helper
    assert 'python scripts/check_target_env.py --strict' in helper
    assert 'bash scripts/ros_target_validation.sh' in helper
    assert 'ros-target-validate-docker' in makefile
    assert 'make ros-target-validate-docker' in readme
    assert 'make ros-target-validate-docker' in validation


def test_readme_documents_repository_and_target_runtime_lanes():
    text = Path('README.md').read_text(encoding='utf-8')
    assert 'Repository validation lane' in text
    assert 'Target runtime lane' in text
    assert 'ROS 2: **optional**' in text
    assert 'ROS 2: **Humble**' in text


def test_observability_sink_is_documented_and_excluded_from_release():
    readme = Path('README.md').read_text(encoding='utf-8')
    gateway_readme = Path('gateway/README.md').read_text(encoding='utf-8')
    packaging = Path('scripts/package_release.py').read_text(encoding='utf-8')
    assert 'EMBODIED_ARM_OBSERVABILITY_DIR' in readme
    assert 'EMBODIED_ARM_OBSERVABILITY_DIR' in gateway_readme
    assert "Path('artifacts')" in packaging
