from __future__ import annotations

import json

try:
    import rclpy
    from arm_backend_common.lifecycle_support import ManagedLifecycleNode, lifecycle_main
    from std_msgs.msg import String
    from arm_common import SrvTypes, TopicNames, ServiceNames
    SetMode = SrvTypes.SetMode
except Exception:  # pragma: no cover
    rclpy = None
    ManagedLifecycleNode = object

    def lifecycle_main(factory, args=None):
        del factory, args
        raise RuntimeError('rclpy unavailable')

    String = object
    SetMode = object

    class TopicNames:
        READINESS_UPDATE = '/arm/readiness/update'

    class ServiceNames:
        SET_MODE = '/arm/set_mode'


class ModeCoordinatorNode(ManagedLifecycleNode):
    """Own the public controller-mode mutation service.

    The readiness manager now consumes mode updates instead of owning the
    mutation API directly. This coordinator publishes authoritative mode changes
    onto ``TopicNames.READINESS_UPDATE`` so readiness snapshots and downstream
    gateway projections stay synchronized without coupling service ownership to
    readiness aggregation.
    """

    VALID_MODES = {'boot', 'idle', 'task', 'manual', 'maintenance', 'safe_stop', 'fault'}

    def __init__(self) -> None:
        super().__init__('mode_coordinator')
        self.declare_parameter('publish_period_sec', 0.5)
        self._mode = 'boot'
        self._controller_mode = 'idle'
        self._pub = self.create_managed_publisher(String, TopicNames.READINESS_UPDATE, 10)
        self.create_service(SetMode, ServiceNames.SET_MODE, self._handle_set_mode)
        self.create_timer(float(self.get_parameter('publish_period_sec').value), self._publish_mode_snapshot)

    def _build_update_payload(self) -> dict[str, str]:
        """Build the readiness-update payload owned by the mode coordinator.

        Returns:
            dict[str, str]: Public mode fields forwarded to the readiness manager.

        Raises:
            Does not raise.

        Boundary behavior:
            Runtime phase and task stage are intentionally omitted so readiness
            aggregation preserves those fields from the authoritative runtime
            publishers instead of resetting them on every mode heartbeat.
        """
        return {
            'mode': self._mode,
            'controllerMode': self._controller_mode,
        }

    def _publish_mode_snapshot(self) -> None:
        if not self.runtime_active:
            return
        self._pub.publish(String(data=json.dumps(self._build_update_payload(), ensure_ascii=False)))

    def _normalize_mode(self, mode: str) -> str:
        normalized = str(mode or '').strip().lower()
        if normalized not in self.VALID_MODES:
            raise ValueError(f'unsupported controller mode: {mode}')
        return normalized

    def _handle_set_mode(self, request: SetMode.Request, response: SetMode.Response) -> SetMode.Response:
        """Apply one public controller-mode transition request.

        Args:
            request: SetMode service request with the desired public controller mode.
            response: Mutable service response populated in place.

        Returns:
            SetMode.Response: Response with success flag and authoritative message.

        Raises:
            Does not raise. Invalid mode requests are mapped to deterministic
            failed responses.

        Boundary behavior:
            The service never widens runtime authority. It only updates the
            public controller mode projection and republishes that decision onto
            the readiness update topic.
        """
        if not self.runtime_active:
            response.success = False
            response.message = 'mode coordinator inactive'
            return response
        try:
            mode = self._normalize_mode(str(request.mode or 'idle'))
        except ValueError as exc:
            response.success = False
            response.message = str(exc)
            return response
        self._mode = mode
        self._controller_mode = 'idle' if mode == 'boot' else mode
        self._publish_mode_snapshot()
        response.success = True
        response.message = f'mode set to {mode}'
        return response


def main(args=None) -> None:  # pragma: no cover
    if rclpy is None:
        raise RuntimeError('rclpy unavailable')
    lifecycle_main(ModeCoordinatorNode, args=args)
