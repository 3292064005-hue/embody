from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AttachmentRecord:
    """Serializable attachment record.

    Attributes:
        target_id: Stable target identifier.
        link_name: Robot link the object is attached to.
        metadata: Optional attachment metadata.
    """

    target_id: str
    link_name: str = 'tool0'
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable record."""
        return {
            'targetId': self.target_id,
            'linkName': self.link_name,
            'metadata': dict(self.metadata or {}),
        }


class AttachManager:
    """Track scene attachments for runtime planning and execution.

    The manager keeps attachment records in a simple in-memory store so that the
    scene manager can expose a deterministic runtime snapshot without coupling to
    MoveIt-specific classes in unit tests.
    """

    def __init__(self) -> None:
        """Initialize the attachment store."""
        self._attachments: dict[str, AttachmentRecord] = {}

    @property
    def attachments(self) -> list[dict[str, Any]]:
        """Return the current attachment list as serializable dictionaries."""
        return [record.to_dict() for record in self._attachments.values()]

    def attach(self, target_id: str, *, link_name: str = 'tool0', metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Attach a target to the runtime scene.

        Args:
            target_id: Stable target identifier.
            link_name: Link name used for the attachment.
            metadata: Optional attachment metadata.

        Returns:
            dict[str, Any]: Serializable attachment record.

        Raises:
            ValueError: If ``target_id`` or ``link_name`` are empty.
        """
        if not str(target_id).strip():
            raise ValueError('target_id must be non-empty')
        if not str(link_name).strip():
            raise ValueError('link_name must be non-empty')
        record = AttachmentRecord(target_id=str(target_id).strip(), link_name=str(link_name).strip(), metadata=dict(metadata or {}))
        self._attachments[record.target_id] = record
        return record.to_dict()

    def detach(self, target_id: str) -> dict[str, Any]:
        """Detach a target from the runtime scene.

        Args:
            target_id: Stable target identifier.

        Returns:
            dict[str, Any]: Serializable detachment result.

        Raises:
            ValueError: If ``target_id`` is empty.
        """
        if not str(target_id).strip():
            raise ValueError('target_id must be non-empty')
        removed = self._attachments.pop(str(target_id).strip(), None)
        return {
            'targetId': str(target_id).strip(),
            'detached': removed is not None,
        }

    def snapshot(self) -> list[dict[str, Any]]:
        """Return the attachment snapshot."""
        return self.attachments
