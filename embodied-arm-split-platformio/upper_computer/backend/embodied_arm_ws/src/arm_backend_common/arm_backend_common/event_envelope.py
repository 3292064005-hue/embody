from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


EVENT_ENVELOPE_SCHEMA_VERSION = '1.0'


@dataclass(slots=True)
class RuntimeEventEnvelope:
    """Structured runtime event metadata serialized through legacy message fields.

    The repository must preserve existing ROS message contracts. This envelope is
    therefore serialized into string fields such as ``TaskEvent.message`` without
    adding new transport fields. Consumers that are unaware of the envelope still
    receive a valid string payload, while envelope-aware consumers can recover the
    structured metadata.
    """

    message: str
    request_id: str | None = None
    correlation_id: str | None = None
    task_run_id: str | None = None
    stage: str | None = None
    error_code: str | None = None
    operator_actionable: bool | None = None
    payload: dict[str, Any] | None = None
    schema_version: str = EVENT_ENVELOPE_SCHEMA_VERSION

    def to_json(self) -> str:
        data = {
            'schemaVersion': self.schema_version,
            'message': self.message,
            'requestId': self.request_id,
            'correlationId': self.correlation_id,
            'taskRunId': self.task_run_id,
            'stage': self.stage,
            'errorCode': self.error_code,
            'operatorActionable': self.operator_actionable,
            'payload': self.payload or {},
        }
        return json.dumps(data, ensure_ascii=False)


def encode_event_message(
    message: str,
    *,
    request_id: str | None = None,
    correlation_id: str | None = None,
    task_run_id: str | None = None,
    stage: str | None = None,
    error_code: str | None = None,
    operator_actionable: bool | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    """Serialize structured runtime event metadata into a string field."""
    if not any((request_id, correlation_id, task_run_id, stage, error_code, operator_actionable is not None, payload)):
        return str(message)
    envelope = RuntimeEventEnvelope(
        message=str(message),
        request_id=request_id,
        correlation_id=correlation_id,
        task_run_id=task_run_id,
        stage=stage,
        error_code=error_code,
        operator_actionable=operator_actionable,
        payload=dict(payload or {}),
    )
    return envelope.to_json()


def decode_event_message(raw: str | None) -> dict[str, Any] | None:
    """Parse a structured runtime event envelope from a message string.

    Returns ``None`` when the payload is not an encoded envelope.
    """
    text = str(raw or '').strip()
    if not text.startswith('{'):
        return None
    try:
        payload = json.loads(text)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if 'message' not in payload or 'schemaVersion' not in payload:
        return None
    return payload
