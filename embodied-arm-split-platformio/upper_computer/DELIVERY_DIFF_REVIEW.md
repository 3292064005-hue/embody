--- original/gateway/api_common.py
+++ modified/gateway/api_common.py
@@ -7,6 +7,7 @@
 
 from .lifespan import CTX
 from .models import new_request_id, now_iso
+from .runtime_projection import ProjectionTopic
 from .security import normalize_role
 
 
@@ -20,7 +21,20 @@
     return normalize_role(request.headers.get('X-Operator-Role'))
 
 
-def append_audit(action: str, status: str, request_id: str, role: str, *, message: str, payload: dict[str, Any] | None = None, task_id: str | None = None, correlation_id: str | None = None) -> dict[str, Any]:
+def append_audit(
+    action: str,
+    status: str,
+    request_id: str,
+    role: str,
+    *,
+    message: str,
+    payload: dict[str, Any] | None = None,
+    task_id: str | None = None,
+    correlation_id: str | None = None,
+    stage: str | None = None,
+    error_code: str | None = None,
+    operator_actionable: bool | None = None,
+) -> dict[str, Any]:
     """Append and return an audit record."""
     record = {
         'id': new_request_id('audit'),
@@ -31,13 +45,29 @@
         'requestId': request_id,
         'correlationId': correlation_id,
         'taskId': task_id,
+        'stage': stage,
+        'errorCode': error_code,
+        'operatorActionable': operator_actionable,
         'message': message,
         'payload': payload or {},
     }
     return CTX.state.append_audit(record)
 
 
-def append_log(level: str, module: str, event: str, message: str, *, task_id: str | None = None, request_id: str | None = None, correlation_id: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
+def append_log(
+    level: str,
+    module: str,
+    event: str,
+    message: str,
+    *,
+    task_id: str | None = None,
+    request_id: str | None = None,
+    correlation_id: str | None = None,
+    payload: dict[str, Any] | None = None,
+    stage: str | None = None,
+    error_code: str | None = None,
+    operator_actionable: bool | None = None,
+) -> dict[str, Any]:
     """Append and return a log record."""
     record = {
         'id': new_request_id('log'),
@@ -47,6 +77,9 @@
         'taskId': task_id,
         'requestId': request_id,
         'correlationId': correlation_id,
+        'stage': stage,
+        'errorCode': error_code,
+        'operatorActionable': operator_actionable,
         'event': event,
         'message': message,
         'payload': payload or {},
@@ -54,33 +87,26 @@
     return CTX.state.append_log(record)
 
 
-async def publish_runtime_state(*, include_system: bool = False, include_hardware: bool = False, include_task: bool = False, include_targets: bool = False) -> None:
-    """Publish the latest runtime snapshots to all WebSocket subscribers."""
+async def publish_runtime_state(*, include_system: bool = False, include_hardware: bool = False, include_task: bool = False, include_targets: bool = False, include_calibration: bool = False) -> None:
+    """Publish the latest runtime projections to all websocket subscribers."""
+    topics: list[ProjectionTopic] = []
     if include_system:
-        await CTX.ws.publish('system.state.updated', CTX.state.get_system())
+        topics.append('system')
     if include_hardware:
-        await CTX.ws.publish('hardware.state.updated', CTX.state.get_hardware())
+        topics.append('hardware')
     if include_task:
-        await CTX.ws.publish('task.progress.updated', CTX.state.get_current_task())
+        topics.append('task')
     if include_targets:
-        await CTX.ws.publish('vision.targets.updated', CTX.state.get_targets())
-    await CTX.ws.publish('readiness.state.updated', CTX.state.get_readiness())
-    await CTX.ws.publish('diagnostics.summary.updated', CTX.state.get_diagnostics())
+        topics.append('targets')
+    if include_calibration:
+        topics.append('calibration')
+    topics.extend(['readiness', 'diagnostics'])
+    await CTX.events.publish_topics(*topics)
 
 
 async def send_ws_initial_snapshot(websocket: WebSocket) -> None:
     """Send the initial WS snapshot to a newly connected client."""
-    await CTX.ws.send_initial_snapshot(
-        websocket,
-        [
-            ('system.state.updated', CTX.state.get_system()),
-            ('readiness.state.updated', CTX.state.get_readiness()),
-            ('vision.targets.updated', CTX.state.get_targets()),
-            ('task.progress.updated', CTX.state.get_current_task()),
-            ('hardware.state.updated', CTX.state.get_hardware()),
-            ('diagnostics.summary.updated', CTX.state.get_diagnostics()),
-        ],
-    )
+    await CTX.events.send_initial_snapshot(websocket)
 
 
 async def handle_ws_client_message(websocket: WebSocket, raw: str) -> None:
@@ -90,6 +116,17 @@
     except Exception:
         return
     if payload.get('event') == 'client.ping':
-        await websocket.send_text(json.dumps({'event': 'server.pong', 'timestamp': now_iso(), 'source': 'gateway', 'schemaVersion': '1.0', 'data': {'sentAt': now_iso()}}, ensure_ascii=False))
+        await websocket.send_text(
+            json.dumps(
+                {
+                    'event': 'server.pong',
+                    'timestamp': now_iso(),
+                    'source': 'gateway',
+                    'schemaVersion': '1.0',
+                    'data': {'sentAt': now_iso()},
+                },
+                ensure_ascii=False,
+            )
+        )
     elif payload.get('event') == 'client.replay_recent':
         await CTX.ws.replay_recent(websocket, limit=int(payload.get('data', {}).get('limit', 5)))

--- original/gateway/lifespan.py
+++ modified/gateway/lifespan.py
@@ -1,38 +1,100 @@
 from __future__ import annotations
-import asyncio, os
+
+import asyncio
+import os
 from contextlib import asynccontextmanager
 from pathlib import Path
+
 from .models import default_system_state
 from .ros_bridge import RosBridge
+from .runtime_projection import RuntimeProjectionService
+from .runtime_publisher import RuntimeEventPublisher
 from .state import GatewayState
 from .storage import CalibrationStorage
 from .ws_manager import WebSocketManager
+
+
 class AppContext:
+    """Gateway application context shared by routers and websocket handlers."""
+
     def __init__(self) -> None:
         project_root = Path(__file__).resolve().parents[1]
-        active_calibration_path = Path(os.environ.get('EMBODIED_ARM_ACTIVE_CALIBRATION_PATH', project_root / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config' / 'default_calibration.yaml'))
+        active_calibration_path = Path(
+            os.environ.get(
+                'EMBODIED_ARM_ACTIVE_CALIBRATION_PATH',
+                project_root / 'backend' / 'embodied_arm_ws' / 'src' / 'arm_bringup' / 'config' / 'default_calibration.yaml',
+            )
+        )
         storage_root = Path(os.environ.get('EMBODIED_ARM_GATEWAY_DATA_DIR', project_root / 'gateway_data'))
-        self.state = GatewayState(); self.ws = WebSocketManager(); self.storage = CalibrationStorage(storage_root, active_calibration_path); self.ros = RosBridge(self.state, lambda e,d: asyncio.create_task(self.ws.publish(e,d)), active_calibration_path); self.heartbeat_task = None
+        self.state = GatewayState()
+        self.ws = WebSocketManager()
+        self.storage = CalibrationStorage(storage_root, active_calibration_path)
+        self.projection = RuntimeProjectionService(self.state)
+        self.events = RuntimeEventPublisher(self.ws, self.projection)
+        self.ros = RosBridge(self.state, self.events, active_calibration_path)
+        self.heartbeat_task: asyncio.Task | None = None
+
     async def start(self) -> None:
-        profile = self.storage.load_active_profile(); versions = self.storage.load_versions(); self.state.set_calibration(profile); self.state.set_calibration_versions(versions); self.state.update_readiness('calibration', True, 'profile_loaded'); self.state.update_readiness('profiles', True, 'profiles_loaded'); self.state.refresh_diagnostics()
-        try: self.ros.start()
-        except Exception as exc: self.state.append_log({'id':'log-bootstrap','timestamp':self.state.timestamp(),'level':'warn','module':'gateway.bootstrap','taskId':None,'requestId':None,'correlationId':None,'event':'ros.start_failed','message':str(exc),'payload':{}})
+        """Initialize storage, event loop bindings, and ROS connectivity."""
+        self.events.set_loop(asyncio.get_running_loop())
+        profile = self.storage.load_active_profile()
+        versions = self.storage.load_versions()
+        self.state.set_calibration(profile)
+        self.state.set_calibration_versions(versions)
+        self.state.update_readiness('calibration', True, 'profile_loaded')
+        self.state.update_readiness('profiles', True, 'profiles_loaded')
+        self.state.refresh_diagnostics()
+        try:
+            self.ros.start()
+        except Exception as exc:  # pragma: no cover - defensive bootstrap logging
+            self.state.append_log(
+                {
+                    'id': 'log-bootstrap',
+                    'timestamp': self.state.timestamp(),
+                    'level': 'warn',
+                    'module': 'gateway.bootstrap',
+                    'taskId': None,
+                    'requestId': None,
+                    'correlationId': None,
+                    'event': 'ros.start_failed',
+                    'message': str(exc),
+                    'payload': {},
+                }
+            )
         if not self.ros.available:
-            system = default_system_state(); system['mode'] = 'idle'; system['faultMessage'] = 'ROS2 bridge unavailable; gateway running with simulated local fallback.'; self.state.set_system(system)
+            system = default_system_state()
+            system['mode'] = 'idle'
+            system['faultMessage'] = 'ROS2 bridge unavailable; gateway running with simulated local fallback.'
+            self.state.set_system(system)
         self.heartbeat_task = asyncio.create_task(self._heartbeat())
+
     async def _heartbeat(self) -> None:
+        """Publish low-frequency health projections and websocket pong frames."""
         while True:
-            await asyncio.sleep(2.0); self.state.refresh_diagnostics(); await self.ws.publish('server.pong', {'sentAt':self.state.timestamp()}); await self.ws.publish('diagnostics.summary.updated', self.state.get_diagnostics()); await self.ws.publish('system.state.updated', self.state.get_system()); await self.ws.publish('hardware.state.updated', self.state.get_hardware())
+            await asyncio.sleep(2.0)
+            self.state.refresh_diagnostics()
+            await self.ws.publish('server.pong', {'sentAt': self.state.timestamp()})
+            await self.events.publish_topics('diagnostics', 'system', 'hardware')
+
     async def stop(self) -> None:
+        """Stop the gateway runtime."""
         if self.heartbeat_task:
             self.heartbeat_task.cancel()
-            try: await self.heartbeat_task
-            except BaseException: pass
+            try:
+                await self.heartbeat_task
+            except BaseException:
+                pass
         self.ros.stop()
+
+
 CTX = AppContext()
+
+
 @asynccontextmanager
 async def lifespan(app):
     app.state.ctx = CTX
     await CTX.start()
-    try: yield
-    finally: await CTX.stop()
+    try:
+        yield
+    finally:
+        await CTX.stop()

--- original/gateway/ros_bridge.py
+++ modified/gateway/ros_bridge.py
@@ -5,13 +5,14 @@
 import os
 import threading
 from pathlib import Path
-from typing import Any, Callable
+from typing import Any
 
 from .models import map_hardware_state_message, map_log_event_message, map_system_state_message, map_target_message, now_iso
 from .ros_contract import (
     ActionNames, ActivateCalibrationVersion, HardwareState, HomeArm, Homing, PickPlaceTask, Recover, ResetFault,
     ServiceNames, SetMode, StartTask, StopTask, SystemState, TargetInfo, TaskEvent, TopicNames,
 )
+from .runtime_publisher import RuntimeEventPublisher
 from .state import GatewayState
 
 try:
@@ -59,9 +60,9 @@
 
 
 class RosBridge:
-    def __init__(self, state: GatewayState, publish_event: Callable[[str, Any], None], active_calibration_path: Path) -> None:
+    def __init__(self, state: GatewayState, publisher: RuntimeEventPublisher, active_calibration_path: Path) -> None:
         self.state = state
-        self.publish_event = publish_event
+        self.publisher = publisher
         self.active_calibration_path = active_calibration_path
         self.available = RCLPY_AVAILABLE
         self._executor = None
@@ -82,7 +83,7 @@
             return
         if not rclpy.ok():
             rclpy.init(args=None)
-        self._node = GatewayRosNode(self.state, self.publish_event)
+        self._node = GatewayRosNode(self.state, self.publisher)
         self._executor = MultiThreadedExecutor()
         self._executor.add_node(self._node)
         self._thread = threading.Thread(target=self._executor.spin, daemon=True)
@@ -267,10 +268,10 @@
 
 if RCLPY_AVAILABLE:
     class GatewayRosNode(Node):
-        def __init__(self, state: GatewayState, publish_event: Callable[[str, Any], None]) -> None:
+        def __init__(self, state: GatewayState, publisher: RuntimeEventPublisher) -> None:
             super().__init__('arm_hmi_gateway_node')
             self._state = state
-            self._publish_event = publish_event
+            self._publisher = publisher
             self._hardware_cmd_pub = self.create_publisher(String, TopicNames.INTERNAL_HARDWARE_CMD, 20)
             self._home_client = self.create_client(HomeArm, ServiceNames.HOME)
             self._reset_fault_client = self.create_client(ResetFault, ServiceNames.RESET_FAULT)
@@ -415,21 +416,13 @@
 
         def _maintenance_tick(self) -> None:
             self._state.prune_targets()
-            self._publish_event('vision.targets.updated', self._state.get_targets())
-            self._publish_event('system.state.updated', self._state.get_system())
-            self._publish_event('hardware.state.updated', self._state.get_hardware())
-            self._publish_event('task.progress.updated', self._state.get_current_task())
-            self._publish_event('readiness.state.updated', self._state.get_readiness())
-            self._publish_event('diagnostics.summary.updated', self._state.get_diagnostics())
+            self._publisher.publish_topics_threadsafe('targets', 'system', 'hardware', 'task', 'readiness', 'diagnostics')
 
         def _on_system_state(self, msg: SystemState) -> None:
             payload = map_system_state_message(msg, ros_connected=True, hardware_state=self._state.get_hardware())
             self._state.set_system(payload)
             task_payload = self._state.sync_task_from_system(payload)
-            self._publish_event('system.state.updated', self._state.get_system())
-            self._publish_event('task.progress.updated', task_payload)
-            self._publish_event('readiness.state.updated', self._state.get_readiness())
-            self._publish_event('diagnostics.summary.updated', self._state.get_diagnostics())
+            self._publisher.publish_topics_threadsafe('system', 'task', 'readiness', 'diagnostics')
 
         def _on_hardware_state(self, msg: HardwareState) -> None:
             payload = map_hardware_state_message(msg, gripper_open=self._state.get_last_gripper_open())
@@ -439,17 +432,12 @@
             system_payload['esp32Connected'] = bool(payload.get('sourceEsp32Online', False))
             system_payload['cameraConnected'] = bool(payload.get('sourceEsp32Online', False))
             self._state.set_system(system_payload)
-            self._publish_event('hardware.state.updated', self._state.get_hardware())
-            self._publish_event('system.state.updated', self._state.get_system())
-            self._publish_event('readiness.state.updated', self._state.get_readiness())
-            self._publish_event('diagnostics.summary.updated', self._state.get_diagnostics())
+            self._publisher.publish_topics_threadsafe('hardware', 'system', 'readiness', 'diagnostics')
 
         def _on_target(self, msg: TargetInfo) -> None:
             payload = map_target_message(msg)
             self._state.upsert_target(payload)
-            self._publish_event('vision.targets.updated', self._state.get_targets())
-            self._publish_event('readiness.state.updated', self._state.get_readiness())
-            self._publish_event('diagnostics.summary.updated', self._state.get_diagnostics())
+            self._publisher.publish_topics_threadsafe('targets', 'readiness', 'diagnostics')
 
         def _on_log_event(self, msg: TaskEvent) -> None:
             payload = map_log_event_message(msg)
@@ -458,8 +446,7 @@
             payload['correlationId'] = correlation_id
             stored = self._state.append_log(payload)
             self._state.update_task_from_log(stored)
-            self._publish_event('log.event.created', stored)
-            self._publish_event('diagnostics.summary.updated', self._state.get_diagnostics())
+            self._publisher.publish_topics_threadsafe('diagnostics', extra_events=[('log.event.created', stored)])
 
         def _on_task_status(self, msg: String) -> None:
             try:
@@ -476,7 +463,7 @@
                 'lastMessage': payload.get('message') or current.get('lastMessage') or '',
             })
             self._state.set_current_task(current if current.get('taskId') else None)
-            self._publish_event('task.progress.updated', self._state.get_current_task())
+            self._publisher.publish_topics_threadsafe('task')
 
         def _on_diagnostics_health(self, msg: String) -> None:
             try:
@@ -488,7 +475,7 @@
             diagnostics['degraded'] = not bool(payload.get('safe', True))
             diagnostics['updatedAt'] = now_iso()
             self._state.set_diagnostics(diagnostics)
-            self._publish_event('diagnostics.summary.updated', self._state.get_diagnostics())
+            self._publisher.publish_topics_threadsafe('diagnostics')
 
         def _on_calibration_profile(self, msg: String) -> None:
             try:
@@ -505,9 +492,7 @@
                 'updatedAt': str(metadata.get('updatedAt', '')) or '',
             }
             self._state.set_calibration(calibration)
-            self._publish_event('calibration.profile.updated', self._state.get_calibration())
-            self._publish_event('readiness.state.updated', self._state.get_readiness())
-            self._publish_event('diagnostics.summary.updated', self._state.get_diagnostics())
+            self._publisher.publish_topics_threadsafe('calibration', 'readiness', 'diagnostics')
 
         def _on_readiness_state(self, msg: String) -> None:
             """Consume the backend-published readiness snapshot."""
@@ -518,5 +503,4 @@
             if not isinstance(payload, dict):
                 return
             self._state.set_readiness_snapshot(payload)
-            self._publish_event('readiness.state.updated', self._state.get_readiness())
-            self._publish_event('diagnostics.summary.updated', self._state.get_diagnostics())
+            self._publisher.publish_topics_threadsafe('readiness', 'diagnostics')

--- original/gateway/storage.py
+++ modified/gateway/storage.py
@@ -1,28 +1,43 @@
 from __future__ import annotations
 
 import json
+import os
+import tempfile
+from contextlib import contextmanager
 from pathlib import Path
-from typing import Any
+from typing import Any, Iterator
 
 import yaml
 
 from .models import default_calibration_profile, now_iso
 
+try:  # pragma: no cover - Linux-only lock path in validated runtime matrix.
+    import fcntl
+except Exception:  # pragma: no cover
+    fcntl = None
+
 
 class CalibrationStorage:
+    """Persistent calibration storage with atomic write and rollback helpers."""
+
     def __init__(self, root_dir: Path, active_yaml_path: Path) -> None:
         self.root_dir = root_dir
         self.active_yaml_path = active_yaml_path
         self.version_index_path = self.root_dir / 'calibration_versions.json'
+        self.active_pointer_path = self.root_dir / 'calibration_active_pointer.json'
+        self.activation_journal_path = self.root_dir / 'calibration_activation_journal.jsonl'
+        self.lock_path = self.root_dir / '.calibration.lock'
         self.root_dir.mkdir(parents=True, exist_ok=True)
 
     def load_active_profile(self) -> dict[str, Any]:
+        """Load the active calibration profile exposed to the frontend."""
         if not self.active_yaml_path.exists():
             return default_calibration_profile()
         payload = yaml.safe_load(self.active_yaml_path.read_text(encoding='utf-8')) or {}
         return self._backend_yaml_to_frontend(payload)
 
     def load_versions(self) -> list[dict[str, Any]]:
+        """Load the persisted profile-version index."""
         if not self.version_index_path.exists():
             active = self.load_active_profile()
             bootstrap = [{
@@ -34,9 +49,12 @@
                 'active': True,
                 'runtimeApplied': False,
                 'runtimeMessage': '',
+                'runtimeState': 'active',
                 **active,
             }]
-            self.version_index_path.write_text(json.dumps(bootstrap, ensure_ascii=False, indent=2), encoding='utf-8')
+            with self._locked_files():
+                self._write_json_atomic(self.version_index_path, bootstrap)
+                self._write_json_atomic(self.active_pointer_path, {'activeProfileId': 'default-profile', 'runtimeState': 'active', 'updatedAt': now_iso()})
             return bootstrap
         try:
             payload = json.loads(self.version_index_path.read_text(encoding='utf-8'))
@@ -45,33 +63,47 @@
             return []
 
     def save_profile(self, profile: dict[str, Any], profile_id: str, operator: str = 'engineering') -> list[dict[str, Any]]:
+        """Persist a new profile version and mark it active atomically.
+
+        Args:
+            profile: Frontend calibration profile payload.
+            profile_id: Stable profile version identifier.
+            operator: Operator label stored in the version record.
+
+        Returns:
+            Updated version index.
+        """
         backend_yaml = self._frontend_to_backend_yaml(profile)
-        self.active_yaml_path.parent.mkdir(parents=True, exist_ok=True)
-        self.active_yaml_path.write_text(yaml.safe_dump(backend_yaml, allow_unicode=True, sort_keys=False), encoding='utf-8')
-        versions = self.load_versions()
-        version_record = {
-            'id': profile_id,
-            'operator': operator,
-            'meanErrorMm': None,
-            'maxErrorMm': None,
-            'sampleCount': None,
-            'active': True,
-            'runtimeApplied': False,
-            'runtimeMessage': '',
-            **profile,
-        }
-        next_versions = [version_record]
-        for item in versions:
-            if item.get('id') == profile_id:
-                continue
-            copied = dict(item)
-            copied['active'] = False
-            copied['runtimeApplied'] = False
-            copied['runtimeMessage'] = ''
-            next_versions.append(copied)
-        self.version_index_path.write_text(json.dumps(next_versions[:20], ensure_ascii=False, indent=2), encoding='utf-8')
-        return next_versions[:20]
-
+        with self._locked_files():
+            versions = self.load_versions()
+            version_record = {
+                'id': profile_id,
+                'operator': operator,
+                'meanErrorMm': None,
+                'maxErrorMm': None,
+                'sampleCount': None,
+                'active': True,
+                'runtimeApplied': False,
+                'runtimeMessage': '',
+                'runtimeState': 'pending_runtime_apply',
+                **profile,
+            }
+            next_versions = [version_record]
+            for item in versions:
+                if item.get('id') == profile_id:
+                    continue
+                copied = dict(item)
+                copied['active'] = False
+                copied['runtimeApplied'] = False
+                copied['runtimeMessage'] = ''
+                copied['runtimeState'] = 'saved'
+                next_versions.append(copied)
+            self.active_yaml_path.parent.mkdir(parents=True, exist_ok=True)
+            self._write_yaml_atomic(self.active_yaml_path, backend_yaml)
+            self._write_json_atomic(self.version_index_path, next_versions[:20])
+            self._write_json_atomic(self.active_pointer_path, {'activeProfileId': profile_id, 'runtimeState': 'pending_runtime_apply', 'updatedAt': now_iso()})
+            self._append_journal({'action': 'save_profile', 'profileId': profile_id, 'operator': operator, 'timestamp': now_iso()})
+            return next_versions[:20]
 
     def snapshot(self) -> dict[str, Any]:
         """Return a serializable storage snapshot for transactional restore.
@@ -85,55 +117,81 @@
         Raises:
             Does not raise.
         """
-        return {'active_profile': self.load_active_profile(), 'versions': self.load_versions()}
+        return {
+            'active_profile': self.load_active_profile(),
+            'versions': self.load_versions(),
+            'active_pointer': self._load_json(self.active_pointer_path, default={'activeProfileId': 'default-profile', 'runtimeState': 'active', 'updatedAt': now_iso()}),
+        }
 
     def restore(self, snapshot: dict[str, Any]) -> None:
-        """Restore a previously captured storage snapshot.
-
-        Args:
-            snapshot: Snapshot returned by :meth:`snapshot`.
-
-        Returns:
-            None.
-
-        Raises:
-            ValueError: If ``snapshot`` is invalid.
-        """
+        """Restore a previously captured storage snapshot."""
         if not isinstance(snapshot, dict):
             raise ValueError('snapshot must be a dictionary')
         active_profile = dict(snapshot.get('active_profile') or default_calibration_profile())
         versions = list(snapshot.get('versions') or [])
+        active_pointer = dict(snapshot.get('active_pointer') or {'activeProfileId': 'default-profile', 'runtimeState': 'active', 'updatedAt': now_iso()})
         backend_yaml = self._frontend_to_backend_yaml(active_profile)
-        self.active_yaml_path.parent.mkdir(parents=True, exist_ok=True)
-        self.active_yaml_path.write_text(yaml.safe_dump(backend_yaml, allow_unicode=True, sort_keys=False), encoding='utf-8')
-        self.version_index_path.write_text(json.dumps(versions[:20], ensure_ascii=False, indent=2), encoding='utf-8')
+        with self._locked_files():
+            self.active_yaml_path.parent.mkdir(parents=True, exist_ok=True)
+            self._write_yaml_atomic(self.active_yaml_path, backend_yaml)
+            self._write_json_atomic(self.version_index_path, versions[:20])
+            self._write_json_atomic(self.active_pointer_path, active_pointer)
+            self._append_journal({'action': 'restore_snapshot', 'timestamp': now_iso(), 'activeProfileId': active_pointer.get('activeProfileId')})
 
     def activate_profile(self, profile_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
-        versions = self.load_versions()
-        target = None
-        next_versions: list[dict[str, Any]] = []
-        for item in versions:
-            copied = dict(item)
-            copied['active'] = copied.get('id') == profile_id
-            copied['runtimeApplied'] = False
-            copied['runtimeMessage'] = ''
-            if copied['active']:
-                target = copied
-            next_versions.append(copied)
-        if target is None:
-            raise KeyError(f'Calibration profile not found: {profile_id}')
-        frontend_profile = {
-            'profileName': target.get('profileName', 'default'),
-            'roi': target.get('roi', default_calibration_profile()['roi']),
-            'tableScaleMmPerPixel': target.get('tableScaleMmPerPixel', 1.0),
-            'offsets': target.get('offsets', {'x': 0.0, 'y': 0.0, 'z': 0.0}),
-            'updatedAt': now_iso(),
-        }
-        backend_yaml = self._frontend_to_backend_yaml(frontend_profile)
-        self.active_yaml_path.parent.mkdir(parents=True, exist_ok=True)
-        self.active_yaml_path.write_text(yaml.safe_dump(backend_yaml, allow_unicode=True, sort_keys=False), encoding='utf-8')
-        self.version_index_path.write_text(json.dumps(next_versions[:20], ensure_ascii=False, indent=2), encoding='utf-8')
-        return frontend_profile, next_versions[:20]
+        """Mark an existing version active and persist the corresponding YAML atomically."""
+        with self._locked_files():
+            versions = self.load_versions()
+            target = None
+            next_versions: list[dict[str, Any]] = []
+            for item in versions:
+                copied = dict(item)
+                copied['active'] = copied.get('id') == profile_id
+                copied['runtimeApplied'] = False
+                copied['runtimeMessage'] = ''
+                copied['runtimeState'] = 'pending_runtime_apply' if copied['active'] else 'saved'
+                if copied['active']:
+                    target = copied
+                next_versions.append(copied)
+            if target is None:
+                raise KeyError(f'Calibration profile not found: {profile_id}')
+            frontend_profile = {
+                'profileName': target.get('profileName', 'default'),
+                'roi': target.get('roi', default_calibration_profile()['roi']),
+                'tableScaleMmPerPixel': target.get('tableScaleMmPerPixel', 1.0),
+                'offsets': target.get('offsets', {'x': 0.0, 'y': 0.0, 'z': 0.0}),
+                'updatedAt': now_iso(),
+            }
+            backend_yaml = self._frontend_to_backend_yaml(frontend_profile)
+            self.active_yaml_path.parent.mkdir(parents=True, exist_ok=True)
+            self._write_yaml_atomic(self.active_yaml_path, backend_yaml)
+            self._write_json_atomic(self.version_index_path, next_versions[:20])
+            self._write_json_atomic(self.active_pointer_path, {'activeProfileId': profile_id, 'runtimeState': 'pending_runtime_apply', 'updatedAt': now_iso()})
+            self._append_journal({'action': 'activate_profile', 'profileId': profile_id, 'timestamp': now_iso()})
+            return frontend_profile, next_versions[:20]
+
+    def mark_runtime_applied(self, profile_id: str, success: bool, message: str) -> list[dict[str, Any]]:
+        """Update runtime-activation markers after ROS apply succeeds or fails."""
+        with self._locked_files():
+            versions = self.load_versions()
+            next_versions: list[dict[str, Any]] = []
+            for item in versions:
+                copied = dict(item)
+                if copied.get('id') == profile_id:
+                    copied['runtimeApplied'] = bool(success)
+                    copied['runtimeMessage'] = str(message)
+                    copied['runtimeState'] = 'active' if success else 'saved'
+                next_versions.append(copied)
+            pointer = {
+                'activeProfileId': profile_id,
+                'runtimeState': 'active' if success else 'pending_runtime_apply',
+                'updatedAt': now_iso(),
+                'runtimeMessage': str(message),
+            }
+            self._write_json_atomic(self.version_index_path, next_versions[:20])
+            self._write_json_atomic(self.active_pointer_path, pointer)
+            self._append_journal({'action': 'runtime_applied', 'profileId': profile_id, 'success': bool(success), 'message': str(message), 'timestamp': now_iso()})
+            return next_versions[:20]
 
     def _frontend_to_backend_yaml(self, profile: dict[str, Any]) -> dict[str, Any]:
         return {
@@ -179,3 +237,49 @@
             'offsets': offsets,
             'updatedAt': metadata.get('updatedAt', now_iso()),
         }
+
+    @contextmanager
+    def _locked_files(self) -> Iterator[None]:
+        """Serialize calibration writes across processes in the validated Linux runtime."""
+        self.root_dir.mkdir(parents=True, exist_ok=True)
+        if fcntl is None:  # pragma: no cover
+            yield
+            return
+        with self.lock_path.open('a+', encoding='utf-8') as handle:
+            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
+            try:
+                yield
+            finally:
+                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
+
+    def _append_journal(self, record: dict[str, Any]) -> None:
+        self.activation_journal_path.parent.mkdir(parents=True, exist_ok=True)
+        line = json.dumps(record, ensure_ascii=False) + os.linesep
+        with self.activation_journal_path.open('a', encoding='utf-8') as handle:
+            handle.write(line)
+            handle.flush()
+            os.fsync(handle.fileno())
+
+    def _write_json_atomic(self, path: Path, payload: Any) -> None:
+        self._write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2))
+
+    def _write_yaml_atomic(self, path: Path, payload: dict[str, Any]) -> None:
+        self._write_text_atomic(path, yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))
+
+    def _write_text_atomic(self, path: Path, text: str) -> None:
+        path.parent.mkdir(parents=True, exist_ok=True)
+        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as handle:
+            handle.write(text)
+            handle.flush()
+            os.fsync(handle.fileno())
+            temp_name = handle.name
+        os.replace(temp_name, path)
+
+    @staticmethod
+    def _load_json(path: Path, *, default: Any) -> Any:
+        if not path.exists():
+            return default
+        try:
+            return json.loads(path.read_text(encoding='utf-8'))
+        except Exception:
+            return default

--- original/gateway/routers/calibration.py
+++ modified/gateway/routers/calibration.py
@@ -0,0 +1,154 @@
+from __future__ import annotations
+
+from fastapi import APIRouter, Request
+
+from ..api_common import append_audit, publish_runtime_state, request_id_from_request, role_from_request
+from ..errors import ApiException, ErrorCode
+from ..lifespan import CTX
+from ..models import new_request_id, now_iso, wrap_response
+from ..schemas import CalibrationProfileRequest
+from ..security import require_role
+
+router = APIRouter()
+
+
+def _ensure_runtime_activation(activation: dict, *, profile_id: str) -> dict:
+    """Validate that ROS runtime activation really succeeded.
+
+    Args:
+        activation: Activation result payload returned by :class:`RosBridge`.
+        profile_id: Profile identifier selected by the gateway.
+
+    Returns:
+        dict: Normalized activation payload.
+
+    Raises:
+        ApiException: Raised when the runtime did not accept the activation.
+    """
+    if not bool((activation or {}).get('success')):
+        raise ApiException(503, str((activation or {}).get('message') or f'calibration activation unavailable for {profile_id}'), error=ErrorCode.INTERNAL_ERROR)
+    return activation
+
+
+def _decorate_versions_with_runtime(versions: list[dict], runtime_profile_id: str, message: str) -> list[dict]:
+    return [
+        {
+            **item,
+            'runtimeApplied': bool(item.get('id') == runtime_profile_id),
+            'runtimeMessage': message,
+        }
+        for item in versions
+    ]
+
+
+@router.get('/api/calibration/profile')
+async def get_calibration_profile(request: Request):
+    return wrap_response(CTX.state.get_calibration(), request_id_from_request(request))
+
+
+@router.get('/api/calibration/versions')
+async def get_calibration_versions(request: Request):
+    return wrap_response(CTX.state.get_calibration_versions(), request_id_from_request(request))
+
+
+@router.get('/api/calibration/profiles')
+async def get_calibration_profiles(request: Request):
+    return wrap_response(CTX.state.get_calibration_versions(), request_id_from_request(request))
+
+
+@router.put('/api/calibration/profile')
+async def put_calibration_profile(body: CalibrationProfileRequest, request: Request):
+    request_id = request_id_from_request(request)
+    role = role_from_request(request)
+    policy = require_role(role, 'maintainer')
+    if not policy.allowed:
+        append_audit('calibration.save', 'blocked', request_id, role, message=policy.reason, payload=body.model_dump())
+        raise ApiException(403, policy.reason, error=ErrorCode.FORBIDDEN)
+    profile_id = new_request_id('cal')
+    storage_snapshot = CTX.storage.snapshot()
+    try:
+        versions = CTX.storage.save_profile({**body.model_dump(), 'updatedAt': now_iso()}, profile_id=profile_id)
+        activation = _ensure_runtime_activation(await CTX.ros.activate_calibration(profile_id=profile_id), profile_id=profile_id)
+    except Exception:
+        CTX.storage.restore(storage_snapshot)
+        raise
+    runtime_profile_id = activation.get('profile_id', profile_id)
+    versions_with_runtime = CTX.storage.mark_runtime_applied(runtime_profile_id, bool(activation.get('success')), str(activation.get('message', '')))
+    calibration_payload = {**body.model_dump(), 'updatedAt': now_iso(), 'runtimeProfileId': runtime_profile_id}
+    CTX.state.set_calibration(calibration_payload)
+    CTX.state.set_calibration_versions(versions_with_runtime)
+    audit = append_audit('calibration.save', 'success', request_id, role, message='calibration saved', payload={'profileId': profile_id})
+    await CTX.ws.publish('audit.event.created', audit)
+    await CTX.ws.publish('calibration.profile.updated', CTX.state.get_calibration())
+    await publish_runtime_state(include_calibration=True)
+    return wrap_response(None, request_id)
+
+
+@router.put('/api/calibration/profiles/{profile_id}/activate')
+async def put_activate_profile(profile_id: str, request: Request):
+    request_id = request_id_from_request(request)
+    role = role_from_request(request)
+    policy = require_role(role, 'maintainer')
+    if not policy.allowed:
+        append_audit('calibration.activate_existing', 'blocked', request_id, role, message=policy.reason, payload={'profileId': profile_id})
+        raise ApiException(403, policy.reason, error=ErrorCode.FORBIDDEN)
+    storage_snapshot = CTX.storage.snapshot()
+    try:
+        profile, versions = CTX.storage.activate_profile(profile_id)
+        activation = _ensure_runtime_activation(await CTX.ros.activate_calibration(profile_id=profile_id), profile_id=profile_id)
+    except Exception:
+        CTX.storage.restore(storage_snapshot)
+        raise
+    runtime_profile_id = activation.get('profile_id', profile_id)
+    versions_with_runtime = CTX.storage.mark_runtime_applied(runtime_profile_id, bool(activation.get('success')), str(activation.get('message', '')))
+    profile_with_runtime = {**profile, 'runtimeProfileId': runtime_profile_id}
+    CTX.state.set_calibration(profile_with_runtime)
+    CTX.state.set_calibration_versions(versions_with_runtime)
+    audit = append_audit('calibration.activate_existing', 'success', request_id, role, message='calibration profile activated', payload={'profileId': profile_id})
+    await CTX.ws.publish('audit.event.created', audit)
+    await CTX.ws.publish('calibration.profile.updated', CTX.state.get_calibration())
+    await publish_runtime_state(include_calibration=True)
+    return wrap_response(None, request_id)
+
+
+@router.post('/api/calibration/reload')
+async def reload_calibration(request: Request):
+    request_id = request_id_from_request(request)
+    role = role_from_request(request)
+    policy = require_role(role, 'maintainer')
+    if not policy.allowed:
+        append_audit('calibration.reload', 'blocked', request_id, role, message=policy.reason)
+        raise ApiException(403, policy.reason, error=ErrorCode.FORBIDDEN)
+    await CTX.ros.reload_calibration()
+    audit = append_audit('calibration.reload', 'success', request_id, role, message='reload triggered')
+    await CTX.ws.publish('audit.event.created', audit)
+    await publish_runtime_state(include_calibration=True)
+    return wrap_response(None, request_id)
+
+
+@router.post('/api/calibration/activate')
+async def activate_calibration(body: CalibrationProfileRequest, request: Request):
+    request_id = request_id_from_request(request)
+    role = role_from_request(request)
+    policy = require_role(role, 'maintainer')
+    if not policy.allowed:
+        append_audit('calibration.activate', 'blocked', request_id, role, message=policy.reason, payload=body.model_dump())
+        raise ApiException(403, policy.reason, error=ErrorCode.FORBIDDEN)
+    profile_id = new_request_id('cal')
+    storage_snapshot = CTX.storage.snapshot()
+    try:
+        versions = CTX.storage.save_profile({**body.model_dump(), 'updatedAt': now_iso()}, profile_id=profile_id)
+        activation = _ensure_runtime_activation(await CTX.ros.activate_calibration(profile_id=profile_id), profile_id=profile_id)
+    except Exception:
+        CTX.storage.restore(storage_snapshot)
+        raise
+    runtime_profile_id = activation.get('profile_id', profile_id)
+    versions_with_runtime = CTX.storage.mark_runtime_applied(runtime_profile_id, bool(activation.get('success')), str(activation.get('message', '')))
+    calibration_payload = {**body.model_dump(), 'updatedAt': now_iso(), 'runtimeProfileId': runtime_profile_id}
+    CTX.state.set_calibration(calibration_payload)
+    CTX.state.set_calibration_versions(versions_with_runtime)
+    audit = append_audit('calibration.activate', 'success', request_id, role, message='calibration profile activated', payload={'profileId': profile_id})
+    await CTX.ws.publish('audit.event.created', audit)
+    await CTX.ws.publish('calibration.profile.updated', CTX.state.get_calibration())
+    await publish_runtime_state(include_calibration=True)
+    return wrap_response(None, request_id)

--- original/gateway/runtime_projection.py
+++ modified/gateway/runtime_projection.py
@@ -0,0 +1,102 @@
+from __future__ import annotations
+
+from dataclasses import dataclass
+from typing import Any, Literal
+
+from .state import GatewayState
+
+ProjectionTopic = Literal['system', 'hardware', 'task', 'targets', 'readiness', 'diagnostics', 'calibration']
+
+PROJECTION_EVENT_BY_TOPIC: dict[ProjectionTopic, str] = {
+    'system': 'system.state.updated',
+    'hardware': 'hardware.state.updated',
+    'task': 'task.progress.updated',
+    'targets': 'vision.targets.updated',
+    'readiness': 'readiness.state.updated',
+    'diagnostics': 'diagnostics.summary.updated',
+    'calibration': 'calibration.profile.updated',
+}
+
+PROJECTION_ORDER: tuple[ProjectionTopic, ...] = (
+    'system',
+    'hardware',
+    'task',
+    'targets',
+    'readiness',
+    'diagnostics',
+    'calibration',
+)
+
+
+@dataclass(frozen=True)
+class ProjectionEvent:
+    """Serializable runtime-projection event.
+
+    Attributes:
+        event: Public websocket event name.
+        data: Serialized payload for the event.
+    """
+
+    event: str
+    data: Any
+
+
+class RuntimeProjectionService:
+    """Build public runtime snapshots from the gateway state container.
+
+    This service intentionally exposes *read-only projections* of the canonical
+    gateway state. Routers and ROS bridge callbacks should publish these
+    projections instead of directly coupling event emission to arbitrary getters.
+    """
+
+    def __init__(self, state: GatewayState) -> None:
+        self._state = state
+
+    def project(self, topic: ProjectionTopic) -> Any:
+        """Return a projected payload for a runtime topic.
+
+        Args:
+            topic: Named runtime projection topic.
+
+        Returns:
+            Snapshot payload corresponding to ``topic``.
+
+        Raises:
+            KeyError: If ``topic`` is not a supported projection.
+        """
+        if topic == 'system':
+            return self._state.get_system()
+        if topic == 'hardware':
+            return self._state.get_hardware()
+        if topic == 'task':
+            return self._state.get_current_task()
+        if topic == 'targets':
+            return self._state.get_targets()
+        if topic == 'readiness':
+            return self._state.get_readiness()
+        if topic == 'diagnostics':
+            return self._state.get_diagnostics()
+        if topic == 'calibration':
+            return self._state.get_calibration()
+        raise KeyError(f'unsupported projection topic: {topic}')
+
+    def build_events(self, *topics: ProjectionTopic) -> list[ProjectionEvent]:
+        """Build ordered, de-duplicated projection events.
+
+        Args:
+            topics: Runtime projection topics to materialize.
+
+        Returns:
+            Ordered list of public websocket events.
+        """
+        requested = {topic for topic in topics}
+        events: list[ProjectionEvent] = []
+        for topic in PROJECTION_ORDER:
+            if topic not in requested:
+                continue
+            events.append(ProjectionEvent(PROJECTION_EVENT_BY_TOPIC[topic], self.project(topic)))
+        return events
+
+    def initial_snapshot_events(self) -> list[ProjectionEvent]:
+        """Return the canonical websocket bootstrap snapshot."""
+        return self.build_events('system', 'readiness', 'targets', 'task', 'hardware', 'diagnostics')

--- original/gateway/runtime_publisher.py
+++ modified/gateway/runtime_publisher.py
@@ -0,0 +1,68 @@
+from __future__ import annotations
+
+import asyncio
+from typing import Any, Iterable
+
+from .runtime_projection import ProjectionEvent, ProjectionTopic, RuntimeProjectionService
+from .ws_manager import WebSocketManager
+
+
+class RuntimeEventPublisher:
+    """Thread-safe publisher for gateway runtime events.
+
+    The ROS bridge invokes event publication from a ROS executor thread while the
+    FastAPI app runs on the asyncio event loop. This helper centralizes the
+    projection lookup, de-duplication, ordering, and thread-safe handoff.
+    """
+
+    def __init__(self, ws: WebSocketManager, projection: RuntimeProjectionService) -> None:
+        self._ws = ws
+        self._projection = projection
+        self._loop: asyncio.AbstractEventLoop | None = None
+
+    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
+        """Attach the FastAPI asyncio event loop used for thread-safe publication."""
+        self._loop = loop
+
+    async def publish_topics(self, *topics: ProjectionTopic, extra_events: Iterable[tuple[str, Any]] | None = None) -> None:
+        """Publish ordered runtime projection topics and optional custom events.
+
+        Args:
+            topics: Projection topics to publish.
+            extra_events: Optional non-projection events appended after projections.
+        """
+        projection_events = self._projection.build_events(*topics)
+        for item in projection_events:
+            await self._ws.publish(item.event, item.data)
+        if extra_events:
+            for event_name, payload in extra_events:
+                await self._ws.publish(event_name, payload)
+
+    async def publish_custom(self, event: str, data: Any) -> None:
+        """Publish a single non-projection event."""
+        await self._ws.publish(event, data)
+
+    def publish_topics_threadsafe(self, *topics: ProjectionTopic, extra_events: Iterable[tuple[str, Any]] | None = None) -> None:
+        """Publish runtime topics from any thread.
+
+        Args:
+            topics: Projection topics to publish.
+            extra_events: Optional custom events.
+
+        Raises:
+            RuntimeError: If the asyncio loop has not been attached yet.
+        """
+        if self._loop is None:
+            raise RuntimeError('runtime publisher loop not initialized')
+        asyncio.run_coroutine_threadsafe(self.publish_topics(*topics, extra_events=extra_events), self._loop)
+
+    def publish_custom_threadsafe(self, event: str, data: Any) -> None:
+        """Publish a custom event from any thread."""
+        if self._loop is None:
+            raise RuntimeError('runtime publisher loop not initialized')
+        asyncio.run_coroutine_threadsafe(self.publish_custom(event, data), self._loop)
+
+    async def send_initial_snapshot(self, websocket) -> None:
+        """Send the canonical initial runtime snapshot to a new websocket client."""
+        events = [(item.event, item.data) for item in self._projection.initial_snapshot_events()]
+        await self._ws.send_initial_snapshot(websocket, events)

--- original/frontend/src/composables/useServerStateSync.ts
+++ modified/frontend/src/composables/useServerStateSync.ts
@@ -16,8 +16,15 @@
 import { useDiagnosticsStore } from '@/stores/diagnostics';
 import { useAuditStore } from '@/stores/audit';
 import { subscribeInvalidation, type InvalidationTopic } from '@/shared/runtime/invalidation';
+import { subscribeRuntimeResync } from '@/shared/runtime/resync';
 
-type ResourceDefinition = { topic: InvalidationTopic; intervalMs: number; critical?: boolean; fetcher: () => Promise<unknown>; apply: (payload: unknown) => void };
+type ResourceDefinition = {
+  topic: InvalidationTopic;
+  intervalMs?: number;
+  fetcher: () => Promise<unknown>;
+  apply: (payload: unknown) => void;
+  mode: 'boot' | 'poll';
+};
 
 export function useServerStateSync(): void {
   const systemStore = useSystemStore();
@@ -34,26 +41,30 @@
   const inflight = new Map<InvalidationTopic, Promise<void>>();
   const timers = new Map<InvalidationTopic, number>();
   let unsubscribeInvalidation: (() => void) | null = null;
+  let unsubscribeResync: (() => void) | null = null;
 
   const resources: ResourceDefinition[] = [
-    { topic: 'system', intervalMs: 2500, critical: true, fetcher: fetchSystemSummary, apply: (payload) => systemStore.setState(payload as Awaited<ReturnType<typeof fetchSystemSummary>>) },
-    { topic: 'readiness', intervalMs: 2500, critical: true, fetcher: fetchReadiness, apply: (payload) => readinessStore.setReadiness(payload as Awaited<ReturnType<typeof fetchReadiness>>) },
-    { topic: 'diagnostics', intervalMs: 3500, fetcher: fetchDiagnosticsSummary, apply: (payload) => diagnosticsStore.setSummary(payload as Awaited<ReturnType<typeof fetchDiagnosticsSummary>>) },
-    { topic: 'task.current', intervalMs: 1500, critical: true, fetcher: fetchCurrentTask, apply: (payload) => taskStore.setCurrentTask(payload as Awaited<ReturnType<typeof fetchCurrentTask>>) },
-    { topic: 'task.templates', intervalMs: 30000, fetcher: fetchTaskTemplates, apply: (payload) => taskStore.setTemplates(payload as Awaited<ReturnType<typeof fetchTaskTemplates>>) },
-    { topic: 'task.history', intervalMs: 5000, fetcher: fetchTaskHistory, apply: (payload) => taskStore.setHistory(payload as Awaited<ReturnType<typeof fetchTaskHistory>>) },
-    { topic: 'vision.targets', intervalMs: 2000, critical: true, fetcher: fetchTargets, apply: (payload) => visionStore.setTargets(payload as Awaited<ReturnType<typeof fetchTargets>>) },
-    { topic: 'vision.calibration', intervalMs: 20000, fetcher: fetchCalibrationProfile, apply: (payload) => visionStore.setCalibration(payload as Awaited<ReturnType<typeof fetchCalibrationProfile>>) },
-    { topic: 'vision.versions', intervalMs: 20000, fetcher: fetchCalibrationVersions, apply: (payload) => visionStore.setVersions(payload as Awaited<ReturnType<typeof fetchCalibrationVersions>>) },
-    { topic: 'hardware', intervalMs: 2000, critical: true, fetcher: fetchHardwareState, apply: (payload) => robotStore.setHardwareState(payload as Awaited<ReturnType<typeof fetchHardwareState>>) },
-    { topic: 'logs', intervalMs: 4000, fetcher: fetchLogs, apply: (payload) => logStore.setRecords(payload as Awaited<ReturnType<typeof fetchLogs>>) },
-    { topic: 'audit', intervalMs: 5000, fetcher: fetchAuditLogs, apply: (payload) => auditStore.setRecords(payload as Awaited<ReturnType<typeof fetchAuditLogs>>) }
+    { topic: 'system', fetcher: fetchSystemSummary, apply: (payload) => systemStore.setState(payload as Awaited<ReturnType<typeof fetchSystemSummary>>), mode: 'boot' },
+    { topic: 'readiness', fetcher: fetchReadiness, apply: (payload) => readinessStore.setReadiness(payload as Awaited<ReturnType<typeof fetchReadiness>>), mode: 'boot' },
+    { topic: 'diagnostics', fetcher: fetchDiagnosticsSummary, apply: (payload) => diagnosticsStore.setSummary(payload as Awaited<ReturnType<typeof fetchDiagnosticsSummary>>), mode: 'boot' },
+    { topic: 'task.current', fetcher: fetchCurrentTask, apply: (payload) => taskStore.setCurrentTask(payload as Awaited<ReturnType<typeof fetchCurrentTask>>), mode: 'boot' },
+    { topic: 'vision.targets', fetcher: fetchTargets, apply: (payload) => visionStore.setTargets(payload as Awaited<ReturnType<typeof fetchTargets>>), mode: 'boot' },
+    { topic: 'hardware', fetcher: fetchHardwareState, apply: (payload) => robotStore.setHardwareState(payload as Awaited<ReturnType<typeof fetchHardwareState>>), mode: 'boot' },
+    { topic: 'task.templates', intervalMs: 30000, fetcher: fetchTaskTemplates, apply: (payload) => taskStore.setTemplates(payload as Awaited<ReturnType<typeof fetchTaskTemplates>>), mode: 'poll' },
+    { topic: 'task.history', intervalMs: 5000, fetcher: fetchTaskHistory, apply: (payload) => taskStore.setHistory(payload as Awaited<ReturnType<typeof fetchTaskHistory>>), mode: 'poll' },
+    { topic: 'vision.calibration', intervalMs: 20000, fetcher: fetchCalibrationProfile, apply: (payload) => visionStore.setCalibration(payload as Awaited<ReturnType<typeof fetchCalibrationProfile>>), mode: 'poll' },
+    { topic: 'vision.versions', intervalMs: 20000, fetcher: fetchCalibrationVersions, apply: (payload) => visionStore.setVersions(payload as Awaited<ReturnType<typeof fetchCalibrationVersions>>), mode: 'poll' },
+    { topic: 'logs', intervalMs: 4000, fetcher: fetchLogs, apply: (payload) => logStore.setRecords(payload as Awaited<ReturnType<typeof fetchLogs>>), mode: 'poll' },
+    { topic: 'audit', intervalMs: 5000, fetcher: fetchAuditLogs, apply: (payload) => auditStore.setRecords(payload as Awaited<ReturnType<typeof fetchAuditLogs>>), mode: 'poll' }
   ];
+
+  const bootTopics = resources.filter((item) => item.mode === 'boot').map((item) => item.topic);
+  const polledTopics = resources.filter((item) => item.mode === 'poll').map((item) => item.topic);
 
   function schedule(definition: ResourceDefinition) {
     const existing = timers.get(definition.topic);
     if (existing) window.clearInterval(existing);
-    if (!settingsStore.autoRefresh) return;
+    if (!settingsStore.autoRefresh || definition.mode !== 'poll' || !definition.intervalMs) return;
     const timer = window.setInterval(() => { void refresh(definition.topic); }, definition.intervalMs);
     timers.set(definition.topic, timer);
   }
@@ -67,10 +78,8 @@
         const payload = await definition.fetcher();
         definition.apply(payload);
         connectionStore.markServerSync(new Date().toISOString(), topic);
-        if (definition.critical) connectionStore.setReadonlyDegraded(false);
       } catch (error) {
         connectionStore.incrementSyncError();
-        if (definition.critical && settingsStore.readonlyOnSyncFailure) connectionStore.setReadonlyDegraded(true);
         console.error(`[server-sync] ${topic} failed`, error);
       } finally {
         inflight.delete(topic);
@@ -80,9 +89,22 @@
     return task;
   }
 
+  async function bootstrap(reason: string) {
+    connectionStore.setTransportState(reason === 'initial' ? 'bootstrapping' : 'resyncing');
+    await Promise.allSettled(bootTopics.map((topic) => refresh(topic)));
+    if (connectionStore.gatewayConnected) connectionStore.setTransportState('live');
+  }
+
   function start() {
-    resources.forEach((definition) => { void refresh(definition.topic); schedule(definition); });
-    unsubscribeInvalidation = subscribeInvalidation((topic) => { void refresh(topic); });
+    void bootstrap('initial');
+    polledTopics.forEach((topic) => { void refresh(topic); });
+    resources.forEach((definition) => { schedule(definition); });
+    unsubscribeInvalidation = subscribeInvalidation((topic) => {
+      const definition = resources.find((item) => item.topic === topic);
+      if (!definition || definition.mode !== 'poll') return;
+      void refresh(topic);
+    });
+    unsubscribeResync = subscribeRuntimeResync((reason) => { void bootstrap(reason); });
   }
 
   function stop() {
@@ -90,6 +112,8 @@
     timers.clear();
     unsubscribeInvalidation?.();
     unsubscribeInvalidation = null;
+    unsubscribeResync?.();
+    unsubscribeResync = null;
   }
 
   onMounted(start);

--- original/frontend/src/composables/useHmiRealtime.ts
+++ modified/frontend/src/composables/useHmiRealtime.ts
@@ -9,6 +9,7 @@
 import { useDiagnosticsStore } from '@/stores/diagnostics';
 import { useAuditStore } from '@/stores/audit';
 import { useReadinessStore } from '@/stores/readiness';
+import { requestRuntimeResync } from '@/shared/runtime/resync';
 import type { SystemState } from '@/models/system';
 import type { VisionTarget } from '@/models/vision';
 import type { TaskProgress } from '@/models/task';
@@ -35,8 +36,21 @@
   const readinessStore = useReadinessStore();
   if (!ws) return;
   unsubscribers = [
-    ws.subscribe('connection.open', ({ timestamp }: { timestamp: string }) => { connectionStore.setGatewayConnected(true); connectionStore.markHeartbeat(timestamp); connectionStore.setWsState('open'); connectionStore.setReadonlyDegraded(false); }),
-    ws.subscribe('connection.close', ({ timestamp }: { timestamp: string }) => { connectionStore.setGatewayConnected(false); connectionStore.markHeartbeat(timestamp); connectionStore.setWsState('closed'); }),
+    ws.subscribe('connection.open', ({ timestamp }: { timestamp: string }) => {
+      connectionStore.setGatewayConnected(true);
+      connectionStore.markHeartbeat(timestamp);
+      connectionStore.setWsState('open');
+      connectionStore.setReadonlyDegraded(false);
+      connectionStore.setTransportState('resyncing');
+      requestRuntimeResync('ws-open');
+    }),
+    ws.subscribe('connection.close', ({ timestamp }: { timestamp: string }) => {
+      connectionStore.setGatewayConnected(false);
+      connectionStore.markHeartbeat(timestamp);
+      connectionStore.setWsState('closed');
+      connectionStore.setReadonlyDegraded(true);
+      connectionStore.setTransportState('degraded');
+    }),
     ws.subscribe('connection.state', ({ wsState }: { wsState: Parameters<typeof connectionStore.setWsState>[0] }) => { connectionStore.setWsState(wsState); }),
     ws.subscribe('connection.heartbeat', ({ timestamp }: { timestamp: string }) => { connectionStore.markHeartbeat(timestamp); }),
     ws.subscribe('connection.pong', ({ timestamp }: { timestamp: string }) => { connectionStore.markPong(timestamp); }),
@@ -70,6 +84,7 @@
       connectionStore.setGatewayConnected(true);
       connectionStore.setWsState('open');
       connectionStore.setReadonlyDegraded(false);
+      connectionStore.setTransportState('live');
       const updateHeartbeat = () => {
         const now = new Date().toISOString();
         connectionStore.markHeartbeat(now);
@@ -80,7 +95,11 @@
       if (!mockHeartbeatTimer) mockHeartbeatTimer = window.setInterval(updateHeartbeat, 2000);
       return;
     }
-    if (!ws) { ws = new HmiWebSocket(import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/ws'); registerSubscriptions(); ws.connect(); }
+    if (!ws) {
+      ws = new HmiWebSocket(import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8000/ws');
+      registerSubscriptions();
+      ws.connect();
+    }
   });
 
   onUnmounted(() => {

--- original/frontend/src/stores/connection.ts
+++ modified/frontend/src/stores/connection.ts
@@ -1,5 +1,5 @@
 import { defineStore } from 'pinia';
-import type { ConnectionHealth, ConnectionQuality, WsState } from '@/models/connection';
+import type { ConnectionHealth, ConnectionQuality, TransportState, WsState } from '@/models/connection';
 
 export const useConnectionStore = defineStore('connection', {
   state: (): ConnectionHealth => ({
@@ -15,7 +15,8 @@
     parseErrors: 0,
     syncErrors: 0,
     staleAfterMs: 8000,
-    readonlyDegraded: false
+    readonlyDegraded: false,
+    transportState: 'bootstrapping',
   }),
   getters: {
     isRealtimeStale(state): boolean {
@@ -24,7 +25,7 @@
     },
     quality(state): ConnectionQuality {
       if (!state.gatewayConnected || state.wsState === 'closed' || state.wsState === 'error') return 'offline';
-      if (this.isRealtimeStale || state.parseErrors > 0 || state.syncErrors > 0) return 'degraded';
+      if (this.isRealtimeStale || state.parseErrors > 0 || state.syncErrors > 0 || state.transportState === 'degraded') return 'degraded';
       return 'healthy';
     },
     healthBadge(): 'success' | 'warning' | 'danger' {
@@ -36,23 +37,41 @@
   actions: {
     setWsState(state: WsState) { this.wsState = state; },
     setGatewayConnected(connected: boolean) { this.gatewayConnected = connected; },
+    setTransportState(state: TransportState) { this.transportState = state; },
     markHeartbeat(timestamp: string) { this.lastHeartbeatAt = timestamp; },
     markPong(timestamp: string) { this.lastPongAt = timestamp; },
     markMessage(timestamp: string, latencyMs?: number | null, eventName?: string) {
       this.lastMessageAt = timestamp;
       if (typeof latencyMs === 'number') this.latencyMs = latencyMs;
       if (eventName) this.lastEventName = eventName;
+      if (this.transportState !== 'resyncing') this.transportState = 'live';
     },
     markServerSync(timestamp: string, eventName?: string) {
       this.lastServerSyncAt = timestamp;
       if (eventName) this.lastEventName = eventName;
       this.syncErrors = 0;
+      if (this.transportState === 'bootstrapping' || this.transportState === 'resyncing') {
+        this.transportState = this.gatewayConnected ? 'live' : this.transportState;
+      }
     },
-    incrementReconnect() { this.reconnectAttempts += 1; },
-    incrementParseErrors() { this.parseErrors += 1; },
-    incrementSyncError() { this.syncErrors += 1; },
+    incrementReconnect() {
+      this.reconnectAttempts += 1;
+      this.transportState = 'resyncing';
+    },
+    incrementParseErrors() {
+      this.parseErrors += 1;
+      this.transportState = 'degraded';
+    },
+    incrementSyncError() {
+      this.syncErrors += 1;
+      if (this.gatewayConnected) this.transportState = 'degraded';
+    },
     setStaleAfterMs(value: number) { this.staleAfterMs = value; },
-    setReadonlyDegraded(value: boolean) { this.readonlyDegraded = value; },
+    setReadonlyDegraded(value: boolean) {
+      this.readonlyDegraded = value;
+      if (value) this.transportState = 'degraded';
+      else if (this.gatewayConnected && this.transportState === 'degraded') this.transportState = 'live';
+    },
     resetSession() {
       this.wsState = 'idle';
       this.gatewayConnected = false;
@@ -66,6 +85,7 @@
       this.parseErrors = 0;
       this.syncErrors = 0;
       this.readonlyDegraded = false;
+      this.transportState = 'bootstrapping';
     }
   }
 });

--- original/frontend/src/models/connection.ts
+++ modified/frontend/src/models/connection.ts
@@ -1,5 +1,6 @@
 export type WsState = 'idle' | 'connecting' | 'open' | 'closing' | 'closed' | 'error';
 export type ConnectionQuality = 'healthy' | 'degraded' | 'offline';
+export type TransportState = 'bootstrapping' | 'live' | 'degraded' | 'resyncing';
 
 export interface ConnectionHealth {
   wsState: WsState;
@@ -15,4 +16,5 @@
   syncErrors: number;
   staleAfterMs: number;
   readonlyDegraded: boolean;
+  transportState: TransportState;
 }

--- original/frontend/src/shared/runtime/resync.ts
+++ modified/frontend/src/shared/runtime/resync.ts
@@ -0,0 +1,12 @@
+type ResyncListener = (reason: string) => void;
+
+const listeners = new Set<ResyncListener>();
+
+export function requestRuntimeResync(reason: string): void {
+  listeners.forEach((listener) => listener(reason));
+}
+
+export function subscribeRuntimeResync(listener: ResyncListener): () => void {
+  listeners.add(listener);
+  return () => listeners.delete(listener);
+}

--- original/backend/embodied_arm_ws/src/arm_motion_planner/arm_motion_planner/planner.py
+++ modified/backend/embodied_arm_ws/src/arm_motion_planner/arm_motion_planner/planner.py
@@ -5,11 +5,10 @@
 from typing import Any
 
 from arm_backend_common.data_models import CalibrationProfile, TargetSnapshot, TaskContext
-from arm_grasp_planner import GraspPlannerNode
-from arm_scene_manager import SceneManagerNode
 
 from .errors import InvalidTargetError, PlanningFailedError, WorkspaceViolationError
 from .moveit_client import MoveItClient, PlanResult
+from .providers import GraspPlanProvider, GraspPlannerAdapter, SceneManagerAdapter, SceneSnapshotProvider
 
 POSE_KEYS = ('x', 'y', 'z', 'yaw')
 SUPPORTED_SERVO_AXES = frozenset({'x', 'y', 'z', 'rx', 'ry', 'rz'})
@@ -42,16 +41,16 @@
         workspace: tuple[float, float, float, float] = (-0.35, 0.35, -0.35, 0.35),
         *,
         moveit_client: MoveItClient | None = None,
-        scene_manager: SceneManagerNode | None = None,
-        grasp_planner: GraspPlannerNode | None = None,
+        scene_manager: SceneSnapshotProvider | None = None,
+        grasp_planner: GraspPlanProvider | None = None,
     ) -> None:
         """Initialize the motion planner.
 
         Args:
             workspace: Planner XY workspace bounds.
             moveit_client: Runtime planning adapter.
-            scene_manager: Optional scene manager used to build runtime scene snapshots.
-            grasp_planner: Optional grasp planner used to select grasp candidates.
+            scene_manager: Optional scene-snapshot provider.
+            grasp_planner: Optional grasp-plan provider.
 
         Returns:
             None.
@@ -63,9 +62,8 @@
             raise ValueError('workspace must contain four finite bounds')
         self.workspace = tuple(float(value) for value in workspace)
         self._moveit_client = moveit_client or MoveItClient()
-        self._scene_manager = scene_manager or SceneManagerNode(enable_ros_io=False)
-        self._grasp_planner = grasp_planner or GraspPlannerNode(enable_ros_io=False)
-
+        self._scene_manager = scene_manager or SceneManagerAdapter()
+        self._grasp_planner = grasp_planner or GraspPlannerAdapter()
 
     def _normalize_target_snapshot(self, target: TargetSnapshot | dict[str, Any] | Any) -> TargetSnapshot:
         """Normalize arbitrary target-like inputs into :class:`TargetSnapshot`.
@@ -106,7 +104,18 @@
         )
 
     def _validate_target(self, target: TargetSnapshot) -> None:
-        """Validate a target before planning."""
+        """Validate a target before planning.
+
+        Args:
+            target: Normalized target snapshot.
+
+        Returns:
+            None.
+
+        Raises:
+            InvalidTargetError: If the target confidence or coordinates are invalid.
+            WorkspaceViolationError: If the target is outside the configured XY workspace.
+        """
         min_x, max_x, min_y, max_y = self.workspace
         if target.confidence < 0.5:
             raise InvalidTargetError('target confidence too low')
@@ -116,7 +125,18 @@
             raise WorkspaceViolationError('target outside configured workspace')
 
     def _validate_place_pose(self, pose: dict[str, Any]) -> dict[str, float]:
-        """Validate and normalize a place pose."""
+        """Validate and normalize a place pose.
+
+        Args:
+            pose: Raw placement pose dictionary.
+
+        Returns:
+            dict[str, float]: Normalized placement pose.
+
+        Raises:
+            InvalidTargetError: If required fields are missing or non-finite.
+            WorkspaceViolationError: If the pose is outside the configured workspace.
+        """
         required = {'x', 'y', 'yaw'}
         missing = required.difference(pose)
         if missing:
@@ -130,7 +150,20 @@
         return normalized
 
     def build_pick_place_plan(self, context: TaskContext, target: TargetSnapshot, calibration: CalibrationProfile) -> list[StagePlan]:
-        """Build a task-level pick-and-place stage plan."""
+        """Build a task-level pick-and-place stage plan.
+
+        Args:
+            context: Task context resolved by the orchestrator.
+            target: Target snapshot selected for pickup.
+            calibration: Active calibration profile.
+
+        Returns:
+            list[StagePlan]: Ordered stage plan for execution.
+
+        Raises:
+            InvalidTargetError: If target or calibration data is invalid.
+            WorkspaceViolationError: If target or placement pose violates workspace bounds.
+        """
         target_snapshot = self._normalize_target_snapshot(target)
         self._validate_target(target_snapshot)
         place_pose = self._validate_place_pose(context.active_place_pose or calibration.resolve_place_profile(context.place_profile))
@@ -162,7 +195,17 @@
         ]
 
     def compile_to_planning_requests(self, plan: list[StagePlan]) -> list[dict[str, Any]]:
-        """Compile stage plans into runtime planning requests."""
+        """Compile stage plans into runtime planning requests.
+
+        Args:
+            plan: Ordered stage plan.
+
+        Returns:
+            list[dict[str, Any]]: Serialized runtime planning requests.
+
+        Raises:
+            PlanningFailedError: If a non-gripper stage misses pose fields.
+        """
         requests: list[dict[str, Any]] = []
         for sequence, stage in enumerate(plan, start=1):
             payload = dict(stage.payload)
@@ -193,7 +236,14 @@
         return requests
 
     def runtime_plan_results(self, plan: list[StagePlan]) -> list[PlanResult]:
-        """Compile and execute runtime planning requests via the MoveIt adapter."""
+        """Compile and execute runtime planning requests via the MoveIt adapter.
+
+        Args:
+            plan: Ordered stage plan.
+
+        Returns:
+            list[PlanResult]: Planning results for non-gripper stages.
+        """
         results: list[PlanResult] = []
         for request in self.compile_to_planning_requests(plan):
             if request['requestKind'] == 'gripper':
@@ -205,7 +255,14 @@
         return results
 
     def summarize_plan(self, plan: list[StagePlan]) -> dict[str, Any]:
-        """Return an HMI-friendly summary of a stage plan."""
+        """Return an HMI-friendly summary of a stage plan.
+
+        Args:
+            plan: Ordered stage plan.
+
+        Returns:
+            dict[str, Any]: Render-friendly plan summary.
+        """
         stage_timeouts = [float(stage.payload.get('timeoutSec', 0.0)) for stage in plan]
         first_scene = next((dict(stage.payload.get('sceneSnapshot') or {}) for stage in plan if stage.payload.get('sceneSnapshot')), {})
         first_candidate = next((dict(stage.payload.get('graspCandidate') or {}) for stage in plan if stage.payload.get('graspCandidate')), {})
@@ -222,7 +279,18 @@
         }
 
     def build_servo_command(self, axis: str, delta: float) -> CartesianJogCommand:
-        """Build a validated Cartesian jog command."""
+        """Build a validated Cartesian jog command.
+
+        Args:
+            axis: Servo axis in tool space.
+            delta: Requested displacement in meters or radians.
+
+        Returns:
+            CartesianJogCommand: Validated servo command.
+
+        Raises:
+            ValueError: If axis or delta violate runtime bounds.
+        """
         if axis not in SUPPORTED_SERVO_AXES:
             raise ValueError(f'unsupported servo axis: {axis}')
         if abs(delta) > MAX_SERVO_DELTA:

--- original/backend/embodied_arm_ws/src/arm_motion_planner/arm_motion_planner/providers.py
+++ modified/backend/embodied_arm_ws/src/arm_motion_planner/arm_motion_planner/providers.py
@@ -0,0 +1,54 @@
+from __future__ import annotations
+
+from typing import Any, Protocol, runtime_checkable
+
+from arm_grasp_planner import GraspPlannerNode
+from arm_scene_manager import SceneManagerNode
+
+
+@runtime_checkable
+class SceneSnapshotProvider(Protocol):
+    """Port used by :class:`MotionPlanner` to obtain scene snapshots."""
+
+    def sync_scene(self, payload: dict[str, Any]) -> dict[str, Any]:
+        """Apply a scene-sync payload and return the updated snapshot."""
+
+
+@runtime_checkable
+class GraspPlanProvider(Protocol):
+    """Port used by :class:`MotionPlanner` to obtain grasp plans."""
+
+    def plan(
+        self,
+        target: dict[str, Any],
+        place_zone: dict[str, Any] | None = None,
+        *,
+        failed_ids: list[str] | None = None,
+    ) -> dict[str, Any]:
+        """Return a serialized grasp plan for a target and place zone."""
+
+
+class SceneManagerAdapter:
+    """Default adapter that exposes ``SceneManagerNode`` through the scene port."""
+
+    def __init__(self, node: SceneManagerNode | None = None) -> None:
+        self._node = node or SceneManagerNode(enable_ros_io=False)
+
+    def sync_scene(self, payload: dict[str, Any]) -> dict[str, Any]:
+        return self._node.sync_scene(payload)
+
+
+class GraspPlannerAdapter:
+    """Default adapter that exposes ``GraspPlannerNode`` through the grasp port."""
+
+    def __init__(self, node: GraspPlannerNode | None = None) -> None:
+        self._node = node or GraspPlannerNode(enable_ros_io=False)
+
+    def plan(
+        self,
+        target: dict[str, Any],
+        place_zone: dict[str, Any] | None = None,
+        *,
+        failed_ids: list[str] | None = None,
+    ) -> dict[str, Any]:
+        return self._node.plan(target, place_zone, failed_ids=failed_ids)

--- original/gateway/tests/test_runtime_projection.py
+++ modified/gateway/tests/test_runtime_projection.py
@@ -0,0 +1,37 @@
+from __future__ import annotations
+
+import asyncio
+
+from gateway.runtime_projection import RuntimeProjectionService
+from gateway.runtime_publisher import RuntimeEventPublisher
+from gateway.state import GatewayState
+
+
+class _FakeWs:
+    def __init__(self) -> None:
+        self.events: list[tuple[str, object]] = []
+
+    async def publish(self, event: str, data):
+        self.events.append((event, data))
+
+    async def send_initial_snapshot(self, websocket, events):
+        self.events.extend(events)
+
+
+def test_runtime_projection_builds_ordered_deduplicated_events():
+    state = GatewayState()
+    projection = RuntimeProjectionService(state)
+    events = projection.build_events('readiness', 'system', 'system', 'diagnostics')
+    assert [item.event for item in events] == [
+        'system.state.updated',
+        'readiness.state.updated',
+        'diagnostics.summary.updated',
+    ]
+
+
+def test_runtime_event_publisher_emits_projection_once_per_topic():
+    state = GatewayState()
+    ws = _FakeWs()
+    publisher = RuntimeEventPublisher(ws, RuntimeProjectionService(state))
+    asyncio.run(publisher.publish_topics('system', 'system', 'readiness'))
+    assert [event for event, _ in ws.events] == ['system.state.updated', 'readiness.state.updated']

--- original/gateway/tests/test_calibration_storage_atomic.py
+++ modified/gateway/tests/test_calibration_storage_atomic.py
@@ -0,0 +1,31 @@
+from __future__ import annotations
+
+import json
+from pathlib import Path
+
+from gateway.storage import CalibrationStorage
+
+
+def test_calibration_storage_writes_pointer_and_journal_atomically(tmp_path: Path):
+    storage = CalibrationStorage(tmp_path / 'gateway_data', tmp_path / 'default_calibration.yaml')
+    versions = storage.save_profile(
+        {
+            'profileName': 'lab-a',
+            'roi': {'x': 0, 'y': 0, 'width': 640, 'height': 480},
+            'tableScaleMmPerPixel': 1.0,
+            'offsets': {'x': 0.1, 'y': -0.1, 'z': 0.0},
+            'updatedAt': '2026-04-01T00:00:00Z',
+        },
+        profile_id='cal-1',
+    )
+    assert versions[0]['id'] == 'cal-1'
+    pointer = json.loads((tmp_path / 'gateway_data' / 'calibration_active_pointer.json').read_text(encoding='utf-8'))
+    assert pointer['activeProfileId'] == 'cal-1'
+    assert pointer['runtimeState'] == 'pending_runtime_apply'
+    journal = (tmp_path / 'gateway_data' / 'calibration_activation_journal.jsonl').read_text(encoding='utf-8').strip().splitlines()
+    assert journal
+    assert 'save_profile' in journal[-1]
+
+    updated_versions = storage.mark_runtime_applied('cal-1', True, 'runtime accepted')
+    assert updated_versions[0]['runtimeApplied'] is True
+    assert updated_versions[0]['runtimeState'] == 'active'

--- original/backend/embodied_arm_ws/tests/test_motion_planner_ports.py
+++ modified/backend/embodied_arm_ws/tests/test_motion_planner_ports.py
@@ -0,0 +1,46 @@
+from __future__ import annotations
+
+from arm_backend_common.data_models import CalibrationProfile, TaskContext, TaskRequest
+from arm_motion_planner import MotionPlanner
+
+
+class _FakeSceneProvider:
+    def __init__(self) -> None:
+        self.payloads = []
+
+    def sync_scene(self, payload: dict):
+        self.payloads.append(dict(payload))
+        return {'objectCount': 3, 'attachments': [], 'frame': 'world'}
+
+
+class _FakeGraspProvider:
+    def __init__(self) -> None:
+        self.requests = []
+
+    def plan(self, target: dict, place_zone: dict | None = None, *, failed_ids: list[str] | None = None):
+        self.requests.append((dict(target), dict(place_zone or {}), list(failed_ids or [])))
+        return {'candidate': {'grasp_x': target['table_x'], 'grasp_y': target['table_y'], 'yaw': target['yaw']}}
+
+
+def test_motion_planner_uses_injected_scene_and_grasp_ports():
+    scene = _FakeSceneProvider()
+    grasp = _FakeGraspProvider()
+    planner = MotionPlanner(scene_manager=scene, grasp_planner=grasp)
+    calibration = CalibrationProfile(place_profiles={'bin_red': {'x': 0.2, 'y': 0.1, 'yaw': 0.0}})
+    context = TaskContext.from_request(TaskRequest(task_id='t-1', task_type='pick_place', target_selector='red', place_profile='bin_red'))
+    plan = planner.build_pick_place_plan(
+        context,
+        {
+            'target_id': 'target-1',
+            'target_type': 'cube',
+            'semantic_label': 'red',
+            'table_x': 0.05,
+            'table_y': 0.02,
+            'yaw': 0.0,
+            'confidence': 0.95,
+        },
+        calibration,
+    )
+    assert len(plan) == 8
+    assert scene.payloads and scene.payloads[0]['target']['target_id'] == 'target-1'
+    assert grasp.requests and grasp.requests[0][0]['target_id'] == 'target-1'

--- original/scripts/sync_interface_mirror.py
+++ modified/scripts/sync_interface_mirror.py
@@ -0,0 +1,28 @@
+from __future__ import annotations
+
+import shutil
+from pathlib import Path
+
+ROOT = Path(__file__).resolve().parents[1] / 'backend' / 'embodied_arm_ws' / 'src'
+ARM_INTERFACES = ROOT / 'arm_interfaces'
+ARM_MSGS = ROOT / 'arm_msgs'
+SUBDIRS = ('msg', 'srv', 'action')
+
+
+def main() -> int:
+    for subdir in SUBDIRS:
+        source_dir = ARM_INTERFACES / subdir
+        target_dir = ARM_MSGS / subdir
+        target_dir.mkdir(parents=True, exist_ok=True)
+        for path in target_dir.glob('*'):
+            if path.is_file():
+                path.unlink()
+        for source in sorted(source_dir.glob('*')):
+            if source.is_file():
+                shutil.copy2(source, target_dir / source.name)
+    print('arm_interfaces mirrored into arm_msgs')
+    return 0
+
+
+if __name__ == '__main__':
+    raise SystemExit(main())