from __future__ import annotations

import json
import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class _FlushRequest:
    """Signal object used to synchronously drain the batched writer."""

    completed: threading.Event
    success: bool = False



@dataclass(frozen=True)
class StreamPolicy:
    """Durability policy for a structured event stream.

    Attributes:
        flush_interval_sec: Periodic flush cadence for queued events.
        fsync_interval_sec: Periodic fsync cadence for queued events.
        batch_size: Maximum records per write batch.
    """

    flush_interval_sec: float
    fsync_interval_sec: float
    batch_size: int


class StructuredEventSink:
    """Persist gateway logs/audits as JSONL records.

    The sink is intentionally local and file-based so repository validation runs do
    not depend on any external observability platform. Downstream collection can
    tail or ship the JSONL files to a centralized system.

    Boundary behavior:
        In the default batched mode, writes are queued and persisted by a
        background writer thread. When strict-sync mode is enabled, appends are
        flushed and fsynced inline for stronger durability at higher latency.
    """

    def __init__(self, root: Path, *, strict_sync: bool = False, queue_size: int = 2048) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.strict_sync = bool(strict_sync)
        self._streams = {
            'logs': self.root / 'logs.jsonl',
            'audits': self.root / 'audits.jsonl',
        }
        self._policies = {
            'logs': StreamPolicy(flush_interval_sec=0.25, fsync_interval_sec=1.5, batch_size=64),
            'audits': StreamPolicy(flush_interval_sec=0.10, fsync_interval_sec=0.50, batch_size=32),
        }
        self._queue: queue.Queue[tuple[str, dict[str, Any]] | _FlushRequest | None] = queue.Queue(maxsize=max(int(queue_size), 64))
        self._handles: dict[str, Any] = {}
        self._metrics_lock = threading.RLock()
        self._queue_depth = 0
        self._dropped_records = 0
        self._last_flush_at: str | None = None
        self._last_flush_duration_ms: float | None = None
        self._last_fsync_duration_ms: float | None = None
        self._last_error: str | None = None
        self._closed = False
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None
        if not self.strict_sync:
            self._thread = threading.Thread(target=self._writer_loop, name='gateway-observability-writer', daemon=True)
            self._thread.start()

    @classmethod
    def from_environment(cls, default_root: Path) -> 'StructuredEventSink | None':
        """Construct a sink from environment variables.

        Args:
            default_root: Default directory used when no explicit path override is set.

        Returns:
            A configured sink instance, or ``None`` when observability is disabled.

        Boundary behavior:
            Invalid queue-size values fall back to the default bounded queue depth
            rather than crashing gateway bootstrap.
        """
        raw = os.environ.get('EMBODIED_ARM_OBSERVABILITY_DIR')
        if raw is not None and raw.strip().lower() in {'0', 'off', 'false', 'disabled', 'none'}:
            return None
        sync_mode = os.environ.get('EMBODIED_ARM_OBSERVABILITY_SYNC_MODE', '').strip().lower()
        raw_queue_size = os.environ.get('EMBODIED_ARM_OBSERVABILITY_QUEUE_SIZE', '2048')
        try:
            queue_size = int(raw_queue_size)
        except (TypeError, ValueError):
            queue_size = 2048
        return cls(Path(raw) if raw else default_root, strict_sync=sync_mode == 'strict', queue_size=queue_size)

    def append(self, stream: str, record: dict[str, Any]) -> None:
        """Persist a structured event.

        Args:
            stream: Target stream name, e.g. ``logs`` or ``audits``.
            record: Serializable JSON record.

        Raises:
            KeyError: If the target stream is unknown.
            RuntimeError: If the sink is already closed.
        """
        if stream not in self._streams:
            raise KeyError(f'unknown observability stream: {stream}')
        if self._closed:
            raise RuntimeError('observability sink already closed')
        item = dict(record)
        if self.strict_sync:
            self._write_batch(stream, [item], force_flush=True, force_fsync=True)
            return
        try:
            self._queue.put_nowait((stream, item))
            with self._metrics_lock:
                self._queue_depth = self._queue.qsize()
            self._wake_event.set()
        except queue.Full:
            with self._metrics_lock:
                self._dropped_records += 1
                self._queue_depth = self._queue.qsize()
                self._last_error = 'observability queue full'

    def flush(self) -> bool:
        """Block until queued records are flushed to disk.

        Returns:
            True when all queued records, plus any writer-side pending batches, have
            been flushed to disk before the method returns.
        """
        if self.strict_sync:
            return True
        if self._closed:
            return False
        request = _FlushRequest(completed=threading.Event())
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                self._queue.put(request, timeout=0.05)
                self._wake_event.set()
                if request.completed.wait(timeout=max(deadline - time.monotonic(), 0.01)):
                    return bool(request.success)
                break
            except queue.Full:
                self._wake_event.set()
        self._record_error('observability flush timeout')
        return False

    def close(self) -> None:
        """Flush pending records and stop the background writer.

        Boundary behavior:
            In batched mode the method first drains queued work to disk before it
            enqueues the shutdown sentinel, preventing the writer thread from
            racing against closed file handles when the queue is saturated.
        """
        if self._closed:
            return
        if not self.strict_sync:
            self.flush()
            self._closed = True
            sentinel_enqueued = False
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and not sentinel_enqueued:
                try:
                    self._queue.put(None, timeout=0.05)
                    sentinel_enqueued = True
                except queue.Full:
                    continue
            if not sentinel_enqueued:
                self._record_error('observability close timeout')
            self._wake_event.set()
            if self._thread is not None:
                self._thread.join(timeout=2.0)
        else:
            self._closed = True
        self._flush_handles(force_fsync=True)
        for handle in self._handles.values():
            try:
                handle.close()
            except Exception:
                pass
        self._handles.clear()

    def metrics(self) -> dict[str, Any]:
        with self._metrics_lock:
            return {
                'queueDepth': int(self._queue_depth),
                'droppedRecords': int(self._dropped_records),
                'strictSync': bool(self.strict_sync),
                'lastFlushAt': self._last_flush_at,
                'lastFlushDurationMs': self._last_flush_duration_ms,
                'lastFsyncDurationMs': self._last_fsync_duration_ms,
                'lastError': self._last_error,
            }

    def _record_error(self, error: str) -> None:
        with self._metrics_lock:
            self._last_error = error

    def _handle_for(self, stream: str):
        handle = self._handles.get(stream)
        if handle is None:
            path = self._streams[stream]
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = path.open('a', encoding='utf-8')
            self._handles[stream] = handle
        return handle

    def _write_batch(self, stream: str, records: list[dict[str, Any]], *, force_flush: bool, force_fsync: bool) -> None:
        if not records:
            return
        handle = self._handle_for(stream)
        started = time.perf_counter()
        try:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                handle.write('\n')
            if force_flush or records:
                handle.flush()
            flush_duration_ms = round((time.perf_counter() - started) * 1000.0, 3)
            with self._metrics_lock:
                self._last_flush_at = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                self._last_flush_duration_ms = flush_duration_ms
            if force_fsync:
                fsync_started = time.perf_counter()
                os.fsync(handle.fileno())
                fsync_duration_ms = round((time.perf_counter() - fsync_started) * 1000.0, 3)
                with self._metrics_lock:
                    self._last_fsync_duration_ms = fsync_duration_ms
        except Exception as exc:
            self._record_error(str(exc))
            raise

    def _flush_handles(self, *, force_fsync: bool) -> None:
        for handle in list(self._handles.values()):
            try:
                handle.flush()
                if force_fsync:
                    fsync_started = time.perf_counter()
                    os.fsync(handle.fileno())
                    with self._metrics_lock:
                        self._last_fsync_duration_ms = round((time.perf_counter() - fsync_started) * 1000.0, 3)
            except Exception as exc:
                self._record_error(str(exc))

    def _writer_loop(self) -> None:
        pending: dict[str, list[dict[str, Any]]] = {'logs': [], 'audits': []}
        last_flush = {name: time.monotonic() for name in self._streams}
        last_fsync = {name: time.monotonic() for name in self._streams}
        while not self._stop_event.is_set():
            timeout = 0.1
            flush_request: _FlushRequest | None = None
            try:
                item = self._queue.get(timeout=timeout)
            except queue.Empty:
                item = 'EMPTY'
            if item is None:
                self._stop_event.set()
            elif item != 'EMPTY':
                if isinstance(item, _FlushRequest):
                    flush_request = item
                else:
                    stream, record = item
                    pending[stream].append(record)
                with self._metrics_lock:
                    self._queue_depth = self._queue.qsize()
            now = time.monotonic()
            for stream, records in pending.items():
                policy = self._policies[stream]
                due_flush = records and (
                    len(records) >= policy.batch_size
                    or (now - last_flush[stream]) >= policy.flush_interval_sec
                    or self._stop_event.is_set()
                    or flush_request is not None
                )
                if due_flush:
                    force_fsync = (now - last_fsync[stream]) >= policy.fsync_interval_sec or self._stop_event.is_set() or flush_request is not None
                    batch = list(records)
                    pending[stream].clear()
                    try:
                        self._write_batch(stream, batch, force_flush=True, force_fsync=force_fsync)
                    except Exception:
                        pass
                    last_flush[stream] = time.monotonic()
                    if force_fsync:
                        last_fsync[stream] = last_flush[stream]
            if flush_request is not None:
                self._flush_handles(force_fsync=True)
                flush_request.success = True
                flush_request.completed.set()
                continue
            self._wake_event.wait(timeout=0.05)
            self._wake_event.clear()
        for stream, records in pending.items():
            if records:
                try:
                    self._write_batch(stream, list(records), force_flush=True, force_fsync=True)
                except Exception:
                    pass
