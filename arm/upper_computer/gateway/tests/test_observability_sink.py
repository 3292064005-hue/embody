from __future__ import annotations

import json
from pathlib import Path

from gateway.observability import StructuredEventSink
from gateway.state import GatewayState


class _FailingSink:
    def append(self, stream: str, record: dict) -> None:
        raise OSError('disk full')


def test_gateway_state_persists_logs_and_audits(tmp_path: Path):
    sink = StructuredEventSink(tmp_path / 'obs')
    state = GatewayState(sink=sink)

    log = state.append_log({'id': 'log-1', 'message': 'hello', 'level': 'info'})
    audit = state.append_audit({'id': 'audit-1', 'message': 'world', 'status': 'ok'})
    assert sink.flush() is True

    log_lines = (tmp_path / 'obs' / 'logs.jsonl').read_text(encoding='utf-8').strip().splitlines()
    audit_lines = (tmp_path / 'obs' / 'audits.jsonl').read_text(encoding='utf-8').strip().splitlines()

    assert json.loads(log_lines[-1])['id'] == log['id']
    assert json.loads(audit_lines[-1])['id'] == audit['id']


def test_gateway_state_observability_sink_failures_do_not_break_in_memory_state():
    state = GatewayState(sink=_FailingSink())
    log = state.append_log({'id': 'log-1', 'message': 'hello', 'level': 'info'})
    audit = state.append_audit({'id': 'audit-1', 'message': 'world', 'status': 'ok'})

    assert log['id'] == 'log-1'
    assert audit['id'] == 'audit-1'
    assert state.get_logs()[0]['id'] == 'log-1'
    assert state.get_audits()[0]['id'] == 'audit-1'
    diagnostics = state.get_diagnostics()['observability']
    assert diagnostics['droppedRecords'] == 0
    assert diagnostics['storeFailures'] == 2
    assert diagnostics['lastPersistenceError'] == 'disk full'
    assert diagnostics['sinkWritable'] is False
    assert diagnostics['degraded'] is True


def test_structured_event_sink_handles_invalid_queue_size_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv('EMBODIED_ARM_OBSERVABILITY_QUEUE_SIZE', 'invalid')
    sink = StructuredEventSink.from_environment(tmp_path / 'obs')
    assert sink is not None
    sink.append('logs', {'id': 'log-1', 'message': 'hello'})
    assert sink.flush() is True
    sink.close()


def test_structured_event_sink_close_stops_writer_and_flushes_pending_records(tmp_path: Path):
    sink = StructuredEventSink(tmp_path / 'obs')
    for idx in range(80):
        sink.append('logs', {'id': f'log-{idx}', 'message': f'message-{idx}'})
    sink.close()
    assert sink._thread is not None
    assert not sink._thread.is_alive()
    lines = (tmp_path / 'obs' / 'logs.jsonl').read_text(encoding='utf-8').strip().splitlines()
    assert len(lines) >= 1
    assert json.loads(lines[-1])['id'].startswith('log-')


def test_structured_event_sink_metrics_surface_degraded_state(tmp_path: Path):
    sink = StructuredEventSink(tmp_path / 'obs')
    sink._record_error('fsync failed')
    metrics = sink.metrics()
    assert metrics['sinkWritable'] is False
    assert metrics['degraded'] is True
    assert metrics['lastError'] == 'fsync failed'
    sink.close()


class _FlappingSink:
    def __init__(self) -> None:
        self.fail = True

    def append(self, stream: str, record: dict) -> None:
        if self.fail:
            raise OSError('disk full')


def test_structured_event_sink_flush_reports_failure_when_writer_batch_fails(monkeypatch, tmp_path: Path):
    sink = StructuredEventSink(tmp_path / 'obs')

    def _boom(stream: str, records: list[dict], *, force_flush: bool, force_fsync: bool) -> None:
        raise OSError('writer exploded')

    monkeypatch.setattr(sink, '_write_batch', _boom)
    sink.append('logs', {'id': 'log-1', 'message': 'hello'})
    assert sink.flush() is False
    metrics = sink.metrics()
    assert metrics['lastError'] == 'writer loop flush failed: writer exploded'
    assert metrics['sinkWritable'] is False
    assert metrics['degraded'] is True
    sink.close()


def test_structured_event_sink_clears_error_after_subsequent_successful_write(monkeypatch, tmp_path: Path):
    sink = StructuredEventSink(tmp_path / 'obs')
    original = sink._write_batch
    failed = {'done': False}

    def _flaky(stream: str, records: list[dict], *, force_flush: bool, force_fsync: bool) -> None:
        if not failed['done']:
            failed['done'] = True
            raise OSError('transient flush failure')
        return original(stream, records, force_flush=force_flush, force_fsync=force_fsync)

    monkeypatch.setattr(sink, '_write_batch', _flaky)
    sink.append('logs', {'id': 'log-1', 'message': 'hello'})
    assert sink.flush() is False
    first = sink.metrics()
    assert first['sinkWritable'] is False
    assert first['lastError'] == 'writer loop flush failed: transient flush failure'

    sink.append('logs', {'id': 'log-2', 'message': 'world'})
    assert sink.flush() is True
    recovered = sink.metrics()
    assert recovered['sinkWritable'] is True
    assert recovered['lastError'] is None
    sink.close()


def test_gateway_state_clears_last_persistence_error_after_store_recovery():
    flapping = _FlappingSink()
    state = GatewayState(sink=flapping)

    state.append_log({'id': 'log-1', 'message': 'hello', 'level': 'info'})
    failed = state.get_diagnostics()['observability']
    assert failed['storeFailures'] == 1
    assert failed['lastPersistenceError'] == 'disk full'
    assert failed['sinkWritable'] is False

    flapping.fail = False
    state.append_log({'id': 'log-2', 'message': 'world', 'level': 'info'})
    recovered = state.get_diagnostics()['observability']
    assert recovered['storeFailures'] == 1
    assert recovered['lastPersistenceError'] is None
    assert recovered['sinkWritable'] is True



def test_structured_event_sink_preserves_failed_stream_error_when_other_stream_succeeds_same_flush(monkeypatch, tmp_path: Path):
    sink = StructuredEventSink(tmp_path / 'obs')
    original = sink._write_batch

    def _partial(stream: str, records: list[dict], *, force_flush: bool, force_fsync: bool) -> None:
        if stream == 'logs':
            raise OSError('logs flush failure')
        return original(stream, records, force_flush=force_flush, force_fsync=force_fsync)

    monkeypatch.setattr(sink, '_write_batch', _partial)
    sink.append('logs', {'id': 'log-1', 'message': 'hello'})
    sink.append('audits', {'id': 'audit-1', 'message': 'world'})
    assert sink.flush() is False
    metrics = sink.metrics()
    assert metrics['sinkWritable'] is False
    assert metrics['degraded'] is True
    assert metrics['lastError'] == 'writer loop flush failed: logs flush failure'
    assert metrics['streamErrors'] == {'logs': 'writer loop flush failed: logs flush failure'}
    sink.close()



def test_structured_event_sink_async_writer_handles_task_runs_stream(tmp_path: Path):
    sink = StructuredEventSink(tmp_path / 'obs')
    sink.append('task_runs', {'id': 'task-run-1', 'event': 'task_run.started'})
    assert sink.flush() is True
    lines = (tmp_path / 'obs' / 'task_runs.jsonl').read_text(encoding='utf-8').strip().splitlines()
    assert json.loads(lines[-1])['id'] == 'task-run-1'
    metrics = sink.metrics()
    assert metrics['sinkWritable'] is True
    assert metrics['lastError'] is None
    sink.close()


def test_gateway_state_task_run_persistence_failures_surface_in_diagnostics():
    state = GatewayState(sink=_FailingSink())

    state.start_task('task-1', 'pick-red', request_id='req-1')

    diagnostics = state.get_diagnostics()['observability']
    assert diagnostics['storeFailures'] == 1
    assert diagnostics['lastPersistenceError'] == 'disk full'
    assert diagnostics['sinkWritable'] is False
    assert diagnostics['degraded'] is True
