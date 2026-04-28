from .health import router as health_router
from .system import router as system_router
from .task import router as task_router
from .vision import router as vision_router
from .calibration import router as calibration_router
from .hardware import router as hardware_router
from .diagnostics import router as diagnostics_router
from .ws import router as ws_router

__all__ = [
    'health_router',
    'system_router',
    'task_router',
    'vision_router',
    'calibration_router',
    'hardware_router',
    'diagnostics_router',
    'ws_router',
]
