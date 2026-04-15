from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

MOCK_FRAME_ID = 'camera_optical_frame'
DEFAULT_MOCK_PROFILE = 'authoritative_demo'
_REALISTIC_MOCK_PAYLOAD = [[0]]
_AUTHORITATIVE_TARGETS = (
    {
        'target_id': 'target_red_001',
        'target_type': 'block',
        'semantic_label': 'red',
        'x': 0.16,
        'y': 0.04,
        'yaw': 0.0,
        'confidence': 0.96,
        'u': 312.0,
        'v': 228.0,
        'detectors': ['color', 'contour'],
    },
    {
        'target_id': 'target_blue_001',
        'target_type': 'block',
        'semantic_label': 'blue',
        'x': 0.19,
        'y': -0.03,
        'yaw': 0.0,
        'confidence': 0.94,
        'u': 338.0,
        'v': 244.0,
        'detectors': ['color', 'contour'],
    },
    {
        'target_id': 'target_qr_bin_green',
        'target_type': 'marker',
        'semantic_label': 'green',
        'x': 0.22,
        'y': 0.01,
        'yaw': 0.0,
        'confidence': 0.97,
        'u': 356.0,
        'v': 216.0,
        'qr_text': 'BIN_GREEN',
        'detectors': ['qrcode'],
    },
)


@dataclass
class CaptureFrame:
    """Serializable capture frame used by camera sources."""

    width: int
    height: int
    frame_id: str
    payload: Any


class CaptureBackend:
    """Capture backend that can emit realistic or authoritative mock frames.

    The split runtime uses two distinct mock-camera behaviors:

    * ``authoritative_demo``: emits a deterministic synthetic scene carrying
      structured targets that the active perception stack can consume as the
      authoritative simulation input.
    * ``realistic_empty``: emits a minimal payload without targets so operators
      can exercise the degraded lane where perception waits on external data.
    """

    def __init__(self, source_type: str = 'mock', *, mock_profile: str = DEFAULT_MOCK_PROFILE) -> None:
        """Initialize the capture backend.

        Args:
            source_type: Capture backend source type.
            mock_profile: Mock-scene profile name for ``mock`` sources.

        Raises:
            ValueError: If the backend configuration is invalid.
        """
        if not str(source_type).strip():
            raise ValueError('source_type must be non-empty')
        normalized_profile = str(mock_profile or DEFAULT_MOCK_PROFILE).strip().lower()
        if normalized_profile not in {'authoritative_demo', 'realistic_empty'}:
            raise ValueError('mock_profile must be authoritative_demo or realistic_empty')
        self.source_type = source_type
        self.mock_profile = normalized_profile
        self._frame_counter = 0

    @staticmethod
    def _build_visual_provenance(
        *,
        source_class: str,
        detection_source_mode: str,
        authoritative_target_source: str,
        renderable_preview: bool,
        camera_live: bool,
        frame_ingress_live: bool,
    ) -> dict[str, Any]:
        """Build stable provenance metadata for downstream camera/perception consumers."""
        return {
            'sourceClass': str(source_class or 'unknown'),
            'detectionSourceMode': str(detection_source_mode or 'unknown'),
            'authoritativeTargetSource': str(authoritative_target_source or 'unknown'),
            'renderablePreview': bool(renderable_preview),
            'cameraLive': bool(camera_live),
            'frameIngressLive': bool(frame_ingress_live),
        }

    def _authoritative_mock_payload(self) -> dict[str, Any]:
        self._frame_counter += 1
        provenance = self._build_visual_provenance(
            source_class='synthetic',
            detection_source_mode='synthetic_targets',
            authoritative_target_source='synthetic_perception',
            renderable_preview=True,
            camera_live=False,
            frame_ingress_live=True,
        )
        return {
            'kind': 'synthetic_scene',
            'mockProfile': self.mock_profile,
            'sourceClass': provenance['sourceClass'],
            'detectionSourceMode': provenance['detectionSourceMode'],
            'authoritativeTargetSource': provenance['authoritativeTargetSource'],
            'renderablePreview': provenance['renderablePreview'],
            'cameraLive': provenance['cameraLive'],
            'frameIngressLive': provenance['frameIngressLive'],
            'visualProvenance': provenance,
            'frameSequence': self._frame_counter,
            'targets': [dict(target) for target in _AUTHORITATIVE_TARGETS],
        }

    def _empty_mock_payload(self) -> dict[str, Any]:
        self._frame_counter += 1
        provenance = self._build_visual_provenance(
            source_class='synthetic',
            detection_source_mode='external_topic_required',
            authoritative_target_source='external_topic_required',
            renderable_preview=True,
            camera_live=False,
            frame_ingress_live=True,
        )
        return {
            'kind': 'synthetic_scene',
            'mockProfile': self.mock_profile,
            'sourceClass': provenance['sourceClass'],
            'detectionSourceMode': provenance['detectionSourceMode'],
            'authoritativeTargetSource': provenance['authoritativeTargetSource'],
            'renderablePreview': provenance['renderablePreview'],
            'cameraLive': provenance['cameraLive'],
            'frameIngressLive': provenance['frameIngressLive'],
            'visualProvenance': provenance,
            'frameSequence': self._frame_counter,
            'payload': _REALISTIC_MOCK_PAYLOAD,
            'targets': [],
        }

    def poll(self) -> CaptureFrame:
        payload = self._authoritative_mock_payload() if self.mock_profile == 'authoritative_demo' else self._empty_mock_payload()
        return CaptureFrame(width=640, height=480, frame_id=MOCK_FRAME_ID, payload=payload)

    def stream(self, count: int = 1) -> Iterable[CaptureFrame]:
        for _ in range(max(1, count)):
            yield self.poll()
