from __future__ import annotations

import datetime as _dt
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from .models import coerce_system_state_aliases, infer_task_percent, infer_task_stage, new_correlation_id, new_request_id, normalize_runtime_phase, now_iso
from .observability import StructuredEventSink


@dataclass
class SnapshotStore:
    """Small mutable store for a single projection snapshot."""

    factory: Callable[[], dict[str, Any]]
    _value: dict[str, Any] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._value = self.factory()

    def set(self, payload: dict[str, Any]) -> None:
        self._value = deepcopy(payload)

    def get(self) -> dict[str, Any]:
        return deepcopy(self._value)

    def mutate(self) -> dict[str, Any]:
        return self._value


@dataclass
class RequestContextStore:
    """Track request/correlation ids for task lifecycle correlation."""

    _request_by_task_id: dict[str, str] = field(default_factory=dict)
    _correlation_by_task_id: dict[str, str] = field(default_factory=dict)
    _task_run_by_task_id: dict[str, str] = field(default_factory=dict)
    _episode_by_task_id: dict[str, str] = field(default_factory=dict)

    def attach(self, task_id: str, request_id: str, *, correlation_id: str | None = None, task_run_id: str | None = None, episode_id: str | None = None) -> tuple[str, str, str, str]:
        correlation = correlation_id or new_correlation_id()
        task_run = task_run_id or new_request_id('taskrun')
        episode = episode_id or new_request_id('episode')
        self._request_by_task_id[task_id] = request_id
        self._correlation_by_task_id[task_id] = correlation
        self._task_run_by_task_id[task_id] = task_run
        self._episode_by_task_id[task_id] = episode
        return request_id, correlation, task_run, episode

    def get(self, task_id: str) -> tuple[str | None, str | None, str | None, str | None]:
        return self._request_by_task_id.get(task_id), self._correlation_by_task_id.get(task_id), self._task_run_by_task_id.get(task_id), self._episode_by_task_id.get(task_id)

    def get_payload(self, task_id: str) -> dict[str, str] | None:
        request_id, correlation_id, task_run_id, episode_id = self.get(task_id)
        if not any((request_id, correlation_id, task_run_id, episode_id)):
            return None
        return {
            'requestId': request_id or '',
            'correlationId': correlation_id or '',
            'taskRunId': task_run_id or '',
            'episodeId': episode_id or task_run_id or '',
        }

    def discard(self, task_id: str) -> None:
        self._request_by_task_id.pop(task_id, None)
        self._correlation_by_task_id.pop(task_id, None)
        self._task_run_by_task_id.pop(task_id, None)
        self._episode_by_task_id.pop(task_id, None)


@dataclass
class TargetProjectionStore:
    """Store and prune target snapshots without leaking bookkeeping fields."""

    _targets: dict[str, dict[str, Any]] = field(default_factory=dict)

    def upsert(self, payload: dict[str, Any]) -> None:
        self._targets[str(payload['id'])] = deepcopy(payload)

    def replace_all(self, payloads: list[dict[str, Any]]) -> None:
        self._targets = {str(payload['id']): deepcopy(payload) for payload in payloads if isinstance(payload, dict) and 'id' in payload}

    def clear(self) -> int:
        count = len(self._targets)
        self._targets.clear()
        return count

    def prune(self, *, keep_after_seconds: float) -> int:
        now = _dt.datetime.utcnow().timestamp()
        expired: list[str] = []
        for key, value in self._targets.items():
            ts = value.get('_receivedAt')
            try:
                age = now - _dt.datetime.fromisoformat(str(ts).replace('Z', '+00:00')).timestamp()
            except Exception:
                age = keep_after_seconds + 1.0
            if age > keep_after_seconds:
                expired.append(key)
        for key in expired:
            self._targets.pop(key, None)
        return len(expired)

    def ordered_public(self) -> list[dict[str, Any]]:
        values = [deepcopy(v) for v in self._targets.values()]
        values.sort(key=lambda item: (-(item.get('confidence') or 0.0), item.get('id', '')))
        for item in values:
            item.pop('_receivedAt', None)
        return values

    def has_targets(self) -> bool:
        return bool(self._targets)


@dataclass
class RecordStore:
    """Append-only capped record store with optional observability persistence."""

    stream_name: str
    sink: StructuredEventSink | None = None
    limit: int = 1000
    _records: list[dict[str, Any]] = field(default_factory=list)
    _persist_failures: int = 0
    _last_persistence_error: str | None = None

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        item = deepcopy(record)
        self._records.append(item)
        if len(self._records) > self.limit:
            self._records = self._records[-self.limit:]
        if self.sink is not None:
            try:
                self.sink.append(self.stream_name, record)
                self._last_persistence_error = None
            except Exception as exc:
                self._persist_failures += 1
                self._last_persistence_error = str(exc)
        return deepcopy(item)

    def get(self) -> list[dict[str, Any]]:
        return deepcopy(self._records)

    def persistence_metrics(self) -> dict[str, Any]:
        return {
            'storeFailures': int(self._persist_failures),
            'lastPersistenceError': self._last_persistence_error,
        }

    def count_fault_like(self) -> int:
        return len([item for item in self._records if item.get('level') in {'error', 'fault'}])


@dataclass
class TaskRunLedgerStore:
    """Persist task-run lifecycle events and project durable task history.

    The ledger records start/progress/finish events in a dedicated structured
    stream so task runs survive gateway restarts when an observability sink is
    configured. REST history remains projected from the ledger when available.
    """

    store: RecordStore

    def append_event(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Append one task-run event to the durable ledger.

        Args:
            event: Event name such as ``task_run.started``.
            payload: Serializable task-run payload.

        Returns:
            dict[str, Any]: Persisted record copy.

        Raises:
            Does not raise. Persistence failures are tracked by ``RecordStore``.
        """
        return self.store.append({'event': str(event), **deepcopy(payload)})

    def projected_history(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Project finalized task history entries from ledger events.

        Args:
            limit: Maximum number of history entries to return.

        Returns:
            list[dict[str, Any]]: Newest-first finalized task history entries.
        """
        finished: list[dict[str, Any]] = []
        for item in reversed(self.store.get()):
            if str(item.get('event', '')) != 'task_run.finished':
                continue
            finished.append({
                'taskId': str(item.get('taskId', '')),
                'templateId': str(item.get('templateId', '') or '') or None,
                'taskType': str(item.get('taskType', 'pick_place')),
                'targetCategory': item.get('targetCategory'),
                'placeProfile': str(item.get('placeProfile', '') or '') or None,
                'runtimeTier': str(item.get('runtimeTier', '') or '') or None,
                'startedAt': str(item.get('startedAt', '')),
                'finishedAt': str(item.get('finishedAt', '')),
                'success': bool(item.get('success', False)),
                'retryCount': int(item.get('retryCount', 0) or 0),
                'durationMs': int(item.get('durationMs', 0) or 0),
                'resultMessage': str(item.get('resultMessage', '')),
                'requestId': str(item.get('requestId', '') or '') or None,
                'correlationId': str(item.get('correlationId', '') or '') or None,
                'taskRunId': str(item.get('taskRunId', '') or '') or None,
                'episodeId': str(item.get('episodeId', item.get('taskRunId', '')) or '') or None,
            })
            if len(finished) >= max(1, int(limit)):
                break
        return finished


@dataclass
class TaskProjectionStore:
    """Own current task + history without coupling callers to raw dict fields."""

    request_contexts: RequestContextStore
    ledger: TaskRunLedgerStore | None = None
    _current_task: dict[str, Any] | None = None
    _task_history: list[dict[str, Any]] = field(default_factory=list)

    def start(
        self,
        *,
        task_id: str,
        frontend_task_type: str,
        target_category: str | None,
        request_id: str | None,
        system_state: dict[str, Any],
        correlation_id: str | None = None,
        task_run_id: str | None = None,
        episode_id: str | None = None,
        template_id: str | None = None,
        place_profile: str | None = None,
        runtime_tier: str | None = None,
        graph_key: str | None = None,
    ) -> dict[str, Any]:
        now = now_iso()
        self._current_task = {
            'taskId': task_id,
            'templateId': template_id,
            'taskType': frontend_task_type,
            'graphKey': graph_key,
            'stage': 'created',
            'percent': 0,
            'retryCount': 0,
            'startedAt': now,
            'updatedAt': now,
            'targetCategory': target_category,
            'placeProfile': place_profile,
            'runtimeTier': runtime_tier,
            'lastMessage': '任务已创建',
        }
        system_state['currentTaskId'] = task_id
        system_state['taskStage'] = 'created'
        system_state['runtimePhase'] = 'perception'
        system_state['controllerMode'] = 'task'
        system_state.update(coerce_system_state_aliases(system_state))
        if request_id:
            attached_request_id, attached_correlation_id, attached_task_run_id, attached_episode_id = self.request_contexts.attach(task_id, request_id, correlation_id=correlation_id, task_run_id=task_run_id, episode_id=episode_id)
            self._current_task['requestId'] = attached_request_id
            self._current_task['correlationId'] = attached_correlation_id
            self._current_task['taskRunId'] = attached_task_run_id
            self._current_task['episodeId'] = attached_episode_id
        self._append_ledger_event('task_run.started', self._current_task)
        return deepcopy(self._current_task)

    def sync_from_system(self, system_payload: dict[str, Any], system_state: dict[str, Any]) -> dict[str, Any] | None:
        now = now_iso()
        mode = normalize_runtime_phase(system_payload.get('runtimePhase', system_payload.get('mode', 'idle')))
        task_id = str(system_payload.get('currentTaskId', '') or '')
        current_stage = str(system_payload.get('taskStage', system_payload.get('currentStage', '')) or '')
        message = str(system_payload.get('faultMessage', '') or '')
        if task_id:
            if self._current_task is None or self._current_task.get('taskId') != task_id:
                context_payload = self.request_contexts.get_payload(task_id) or {}
                self._current_task = {
                    'taskId': task_id,
                    'templateId': None,
                    'taskType': 'pick_place',
                    'stage': infer_task_stage(mode, current_stage),
                    'percent': infer_task_percent(mode, current_stage),
                    'retryCount': 0,
                    'startedAt': now,
                    'updatedAt': now,
                    'targetCategory': None,
                    'placeProfile': None,
                    'runtimeTier': None,
                    'lastMessage': message or current_stage or mode,
                    **context_payload,
                }
                self._append_ledger_event('task_run.discovered', self._current_task)
            else:
                self._current_task['stage'] = infer_task_stage(mode, current_stage)
                self._current_task['percent'] = infer_task_percent(mode, current_stage)
                self._current_task['updatedAt'] = now
                self._current_task['lastMessage'] = message or current_stage or mode
                self._append_ledger_event('task_run.progress', self._current_task)
            return deepcopy(self._current_task)
        if self._current_task and mode in {'idle', 'safe_stop', 'fault'}:
            if mode == 'idle' and self._current_task.get('stage') not in {'done', 'failed'}:
                self._finalize_locked(True, message or '任务完成', system_state)
            elif mode in {'safe_stop', 'fault'}:
                self._finalize_locked(False, message or '任务中断', system_state)
        return deepcopy(self._current_task)

    def update_from_log(self, record: dict[str, Any], system_state: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
        task_id = str(record.get('taskId', '') or '')
        event = str(record.get('event', '') or '')
        message = str(record.get('message', '') or '')
        now = now_iso()
        changed = False
        if event == 'TASK_ENQUEUED' and task_id:
            if self._current_task is None:
                context_payload = self.request_contexts.get_payload(task_id) or {}
                self._current_task = {
                    'taskId': task_id,
                    'templateId': None,
                    'taskType': 'pick_place',
                    'stage': 'created',
                    'percent': 0,
                    'retryCount': 0,
                    'startedAt': now,
                    'updatedAt': now,
                    'targetCategory': None,
                    'placeProfile': None,
                    'runtimeTier': None,
                    'lastMessage': message,
                    **context_payload,
                }
            changed = True
        elif event == 'PLAN_OK' and self._current_task:
            self._current_task['stage'] = 'plan'
            self._current_task['percent'] = max(int(self._current_task['percent']), 40)
            self._current_task['updatedAt'] = now
            self._current_task['lastMessage'] = message
            changed = True
        elif event == 'EXEC_STAGE' and self._current_task:
            self._current_task['stage'] = 'execute'
            self._current_task['percent'] = max(int(self._current_task['percent']), 72)
            self._current_task['updatedAt'] = now
            self._current_task['lastMessage'] = message
            changed = True
        elif event == 'TASK_RETRY' and self._current_task:
            self._current_task['stage'] = 'perception'
            self._current_task['retryCount'] = int(self._current_task['retryCount']) + 1
            self._current_task['percent'] = max(15, int(self._current_task['percent']) - 20)
            self._current_task['updatedAt'] = now
            self._current_task['lastMessage'] = message
            changed = True
        elif event == 'TASK_DONE' and self._current_task:
            self._finalize_locked(True, message or '任务完成', system_state)
            changed = True
        elif event in {'SAFE_STOP', 'FAULT'} and self._current_task:
            self._finalize_locked(False, message or '任务失败', system_state)
            changed = True
        if changed and self._current_task is not None:
            self._append_ledger_event('task_run.progress', self._current_task)
        return deepcopy(self._current_task), changed

    def set_current(self, task: dict[str, Any] | None) -> None:
        self._current_task = deepcopy(task) if task else None
        if self._current_task is not None:
            self._append_ledger_event('task_run.shadow_set', self._current_task)

    def get_current(self) -> dict[str, Any] | None:
        return deepcopy(self._current_task)

    def get_history(self) -> list[dict[str, Any]]:
        if self.ledger is not None:
            projected = self.ledger.projected_history(limit=100)
            if projected:
                return projected
        return deepcopy(self._task_history)

    def _duration_ms(self, started_at: str, finished_at: str) -> int:
        try:
            started = _dt.datetime.fromisoformat(str(started_at).replace('Z', '+00:00'))
            finished = _dt.datetime.fromisoformat(str(finished_at).replace('Z', '+00:00'))
            return max(0, int((finished - started).total_seconds() * 1000.0))
        except Exception:
            return 0

    def _append_ledger_event(self, event: str, task_payload: dict[str, Any]) -> None:
        if self.ledger is None:
            return
        self.ledger.append_event(event, dict(task_payload, updatedAt=now_iso()))

    def _finalize_locked(self, success: bool, result_message: str, system_state: dict[str, Any]) -> None:
        if self._current_task is None:
            return
        now = now_iso()
        started_at = self._current_task.get('startedAt', now)
        duration_ms = self._duration_ms(str(started_at), now)
        history_entry = {
            'taskId': self._current_task['taskId'],
            'templateId': self._current_task.get('templateId'),
            'taskType': self._current_task['taskType'],
            'targetCategory': self._current_task.get('targetCategory'),
            'placeProfile': self._current_task.get('placeProfile'),
            'runtimeTier': self._current_task.get('runtimeTier'),
            'startedAt': started_at,
            'finishedAt': now,
            'success': bool(success),
            'retryCount': int(self._current_task.get('retryCount', 0)),
            'durationMs': duration_ms,
            'resultMessage': result_message,
            'requestId': self._current_task.get('requestId'),
            'correlationId': self._current_task.get('correlationId'),
            'taskRunId': self._current_task.get('taskRunId'),
            'episodeId': self._current_task.get('episodeId', self._current_task.get('taskRunId')),
        }
        self._task_history = [history_entry, *self._task_history][:100]
        self._append_ledger_event('task_run.finished', history_entry)
        self.request_contexts.discard(self._current_task['taskId'])
        system_state['currentTaskId'] = ''
        system_state['taskStage'] = 'done' if success else 'failed'
        system_state['runtimePhase'] = 'idle' if success else 'fault'
        system_state['controllerMode'] = 'idle' if success else 'maintenance'
        system_state.update(coerce_system_state_aliases(system_state))
        self._current_task = None
