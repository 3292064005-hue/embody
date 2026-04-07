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
    assert state.get_diagnostics()['observability']['droppedRecords'] == 0


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
