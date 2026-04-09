from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import yaml

from .models import default_calibration_profile, now_iso
from .runtime_config import load_place_profiles

try:  # pragma: no cover - Linux-only lock path in validated runtime matrix.
    import fcntl
except Exception:  # pragma: no cover
    fcntl = None


class CalibrationStorage:
    """Persistent calibration storage with atomic write and rollback helpers."""

    def __init__(self, root_dir: Path, active_yaml_path: Path, default_yaml_path: Path | None = None) -> None:
        """Initialize calibration storage locations.

        Args:
            root_dir: Mutable runtime data directory.
            active_yaml_path: Mutable active calibration YAML path used by the gateway/runtime.
            default_yaml_path: Optional read-only source YAML used as a compatibility fallback.

        Returns:
            None.

        Raises:
            Does not raise.
        """
        self.root_dir = root_dir
        self.active_yaml_path = active_yaml_path
        self.default_yaml_path = default_yaml_path
        self.version_index_path = self.root_dir / 'calibration_versions.json'
        self.active_pointer_path = self.root_dir / 'calibration_active_pointer.json'
        self.activation_journal_path = self.root_dir / 'calibration_activation_journal.jsonl'
        self.lock_path = self.root_dir / '.calibration.lock'
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self._lock_state = threading.local()

    def load_active_profile(self) -> dict[str, Any]:
        """Load the active calibration profile exposed to the frontend.

        The runtime YAML is authoritative. If it does not exist, the method
        falls back to the read-only default source YAML, and finally to a built-in
        default frontend profile.
        """
        payload = self._load_yaml_profile(self.active_yaml_path)
        if payload is None and self.default_yaml_path is not None:
            payload = self._load_yaml_profile(self.default_yaml_path)
        if payload is None:
            return default_calibration_profile()
        return self._backend_yaml_to_frontend(payload)

    def load_versions(self) -> list[dict[str, Any]]:
        """Load the persisted profile-version index."""
        if not self.version_index_path.exists():
            active = self.load_active_profile()
            bootstrap = [{
                'id': 'default-profile',
                'operator': 'system',
                'meanErrorMm': None,
                'maxErrorMm': None,
                'sampleCount': None,
                'active': True,
                'runtimeApplied': False,
                'runtimeMessage': '',
                'runtimeState': 'active',
                **active,
            }]
            with self._locked_files():
                self._write_json_atomic(self.version_index_path, bootstrap)
                self._write_json_atomic(self.active_pointer_path, {'activeProfileId': 'default-profile', 'runtimeState': 'active', 'updatedAt': now_iso()})
            return bootstrap
        try:
            payload = json.loads(self.version_index_path.read_text(encoding='utf-8'))
            return payload if isinstance(payload, list) else []
        except Exception:
            return []

    def save_profile(self, profile: dict[str, Any], profile_id: str, operator: str = 'engineering') -> list[dict[str, Any]]:
        """Persist a new profile version and mark it active atomically.

        Args:
            profile: Frontend calibration profile payload.
            profile_id: Stable profile version identifier.
            operator: Operator label stored in the version record.

        Returns:
            Updated version index.

        Raises:
            TypeError: When the profile payload cannot be serialized by the YAML writer.
            OSError: When the runtime data directory cannot be written.
        """
        backend_yaml = self._frontend_to_backend_yaml(profile)
        with self._locked_files():
            versions = self.load_versions()
            version_record = {
                'id': profile_id,
                'operator': operator,
                'meanErrorMm': None,
                'maxErrorMm': None,
                'sampleCount': None,
                'active': True,
                'runtimeApplied': False,
                'runtimeMessage': '',
                'runtimeState': 'pending_runtime_apply',
                **profile,
            }
            next_versions = [version_record]
            for item in versions:
                if item.get('id') == profile_id:
                    continue
                copied = dict(item)
                copied['active'] = False
                copied['runtimeApplied'] = False
                copied['runtimeMessage'] = ''
                copied['runtimeState'] = 'saved'
                next_versions.append(copied)
            self.active_yaml_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_yaml_atomic(self.active_yaml_path, backend_yaml)
            self._write_json_atomic(self.version_index_path, next_versions[:20])
            self._write_json_atomic(self.active_pointer_path, {'activeProfileId': profile_id, 'runtimeState': 'pending_runtime_apply', 'updatedAt': now_iso()})
            self._append_journal({'action': 'save_profile', 'profileId': profile_id, 'operator': operator, 'timestamp': now_iso()})
            return next_versions[:20]

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable storage snapshot for transactional restore."""
        return {
            'active_profile': self.load_active_profile(),
            'versions': self.load_versions(),
            'active_pointer': self._load_json(self.active_pointer_path, default={'activeProfileId': 'default-profile', 'runtimeState': 'active', 'updatedAt': now_iso()}),
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Restore a previously captured storage snapshot.

        Args:
            snapshot: Snapshot returned by :meth:`snapshot`.

        Returns:
            None.

        Raises:
            ValueError: If ``snapshot`` is not a dictionary.
            OSError: If runtime files cannot be restored.
        """
        if not isinstance(snapshot, dict):
            raise ValueError('snapshot must be a dictionary')
        active_profile = dict(snapshot.get('active_profile') or default_calibration_profile())
        versions = list(snapshot.get('versions') or [])
        active_pointer = dict(snapshot.get('active_pointer') or {'activeProfileId': 'default-profile', 'runtimeState': 'active', 'updatedAt': now_iso()})
        backend_yaml = self._frontend_to_backend_yaml(active_profile)
        with self._locked_files():
            self.active_yaml_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_yaml_atomic(self.active_yaml_path, backend_yaml)
            self._write_json_atomic(self.version_index_path, versions[:20])
            self._write_json_atomic(self.active_pointer_path, active_pointer)
            self._append_journal({'action': 'restore_snapshot', 'timestamp': now_iso(), 'activeProfileId': active_pointer.get('activeProfileId')})

    def activate_profile(self, profile_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Mark an existing version active and persist the corresponding YAML atomically."""
        with self._locked_files():
            versions = self.load_versions()
            target = None
            next_versions: list[dict[str, Any]] = []
            for item in versions:
                copied = dict(item)
                copied['active'] = copied.get('id') == profile_id
                copied['runtimeApplied'] = False
                copied['runtimeMessage'] = ''
                copied['runtimeState'] = 'pending_runtime_apply' if copied['active'] else 'saved'
                if copied['active']:
                    target = copied
                next_versions.append(copied)
            if target is None:
                raise KeyError(f'Calibration profile not found: {profile_id}')
            frontend_profile = {
                'profileName': target.get('profileName', 'default'),
                'roi': target.get('roi', default_calibration_profile()['roi']),
                'tableScaleMmPerPixel': target.get('tableScaleMmPerPixel', 1.0),
                'offsets': target.get('offsets', {'x': 0.0, 'y': 0.0, 'z': 0.0}),
                'updatedAt': now_iso(),
            }
            backend_yaml = self._frontend_to_backend_yaml(frontend_profile)
            self.active_yaml_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_yaml_atomic(self.active_yaml_path, backend_yaml)
            self._write_json_atomic(self.version_index_path, next_versions[:20])
            self._write_json_atomic(self.active_pointer_path, {'activeProfileId': profile_id, 'runtimeState': 'pending_runtime_apply', 'updatedAt': now_iso()})
            self._append_journal({'action': 'activate_profile', 'profileId': profile_id, 'timestamp': now_iso()})
            return frontend_profile, next_versions[:20]

    def mark_runtime_applied(self, profile_id: str, success: bool, message: str) -> list[dict[str, Any]]:
        """Update runtime-activation markers after ROS apply succeeds or fails."""
        with self._locked_files():
            versions = self.load_versions()
            next_versions: list[dict[str, Any]] = []
            for item in versions:
                copied = dict(item)
                if copied.get('id') == profile_id:
                    copied['runtimeApplied'] = bool(success)
                    copied['runtimeMessage'] = str(message)
                    copied['runtimeState'] = 'active' if success else 'saved'
                next_versions.append(copied)
            pointer = {
                'activeProfileId': profile_id,
                'runtimeState': 'active' if success else 'pending_runtime_apply',
                'updatedAt': now_iso(),
                'runtimeMessage': str(message),
            }
            self._write_json_atomic(self.version_index_path, next_versions[:20])
            self._write_json_atomic(self.active_pointer_path, pointer)
            self._append_journal({'action': 'runtime_applied', 'profileId': profile_id, 'success': bool(success), 'message': str(message), 'timestamp': now_iso()})
            return next_versions[:20]

    def _frontend_to_backend_yaml(self, profile: dict[str, Any]) -> dict[str, Any]:
        return {
            'version': profile.get('profileName', 'default'),
            'compensation': {
                'x_bias': float(profile.get('offsets', {}).get('x', 0.0)),
                'y_bias': float(profile.get('offsets', {}).get('y', 0.0)),
                'yaw_bias': 0.0,
            },
            'robot': {
                'pre_grasp_z': 0.12,
                'grasp_z': 0.03,
                'place_z': 0.05,
                'retreat_z': 0.12,
            },
            'placement': {
                'source': 'arm_bringup/config/placement_profiles.yaml',
                'profiles': load_place_profiles(),
            },
            'hmi_metadata': {
                'roi': profile.get('roi', default_calibration_profile()['roi']),
                'tableScaleMmPerPixel': float(profile.get('tableScaleMmPerPixel', 1.0)),
                'offsets': profile.get('offsets', {'x': 0.0, 'y': 0.0, 'z': 0.0}),
                'updatedAt': profile.get('updatedAt', now_iso()),
            },
        }

    def _backend_yaml_to_frontend(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata = payload.get('hmi_metadata', {}) or {}
        compensation = payload.get('compensation', {}) or {}
        offsets = dict(metadata.get('offsets', {}))
        offsets.setdefault('x', float(compensation.get('x_bias', 0.0)))
        offsets.setdefault('y', float(compensation.get('y_bias', 0.0)))
        offsets.setdefault('z', 0.0)
        return {
            'profileName': str(payload.get('version', 'default')),
            'roi': metadata.get('roi', default_calibration_profile()['roi']),
            'tableScaleMmPerPixel': float(metadata.get('tableScaleMmPerPixel', 1.0)),
            'offsets': offsets,
            'updatedAt': metadata.get('updatedAt', now_iso()),
        }

    @contextmanager
    def _locked_files(self) -> Iterator[None]:
        """Serialize calibration writes across processes in the validated Linux runtime."""
        self.root_dir.mkdir(parents=True, exist_ok=True)
        depth = int(getattr(self._lock_state, 'depth', 0))
        if depth > 0 or fcntl is None:  # pragma: no cover
            self._lock_state.depth = depth + 1
            try:
                yield
            finally:
                self._lock_state.depth = max(int(getattr(self._lock_state, 'depth', 1)) - 1, 0)
            return
        with self.lock_path.open('a+', encoding='utf-8') as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            self._lock_state.depth = depth + 1
            try:
                yield
            finally:
                self._lock_state.depth = max(int(getattr(self._lock_state, 'depth', 1)) - 1, 0)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _append_journal(self, record: dict[str, Any]) -> None:
        self.activation_journal_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + os.linesep
        with self.activation_journal_path.open('a', encoding='utf-8') as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def _write_json_atomic(self, path: Path, payload: Any) -> None:
        self._write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2))

    def _write_yaml_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        self._write_text_atomic(path, yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))

    def _write_text_atomic(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
            temp_name = handle.name
        os.replace(temp_name, path)

    @staticmethod
    def _load_json(path: Path, *, default: Any) -> Any:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return default

    @staticmethod
    def _load_yaml_profile(path: Path | None) -> dict[str, Any] | None:
        if path is None or not path.exists():
            return None
        try:
            payload = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None
