from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path

import httpx


def _install_httpx_testclient_compat() -> None:
    """Bridge Starlette TestClient onto newer httpx builds.

    Some environments ship a newer ``httpx`` where ``Client.__init__`` no longer
    accepts the legacy ``app=`` keyword that older Starlette TestClient versions
    still pass. Tests patch the signature locally so repository verification does
    not depend on the host dependency resolver.
    """
    if 'app' in inspect.signature(httpx.Client.__init__).parameters:
        return
    original = httpx.Client.__init__

    def _compat_init(self, *args, app=None, transport=None, **kwargs):
        return original(self, *args, transport=transport, **kwargs)

    httpx.Client.__init__ = _compat_init



def _pin_gateway_tests_to_repo_root() -> None:
    """Normalize gateway test execution to the upper_computer repo root.

    Gateway tests read documentation, workflow, and packaging files from the
    repository root. When pytest is launched from ``upper_computer/gateway`` the
    current working directory is too deep, which makes those path-based
    assertions fail even though the repository is valid. This helper makes test
    execution location-independent by switching to the repo root and ensuring
    it is importable.
    """
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    os.chdir(repo_root)


_install_httpx_testclient_compat()
_pin_gateway_tests_to_repo_root()

# Most gateway integration tests exercise the explicit local HMI development
# profile rather than the default fail-closed target-runtime profile.
os.environ.setdefault('EMBODIED_ARM_RUNTIME_PROFILE', 'dev-hmi-mock')
os.environ.setdefault('EMBODIED_ARM_ALLOW_SIMULATION_FALLBACK', 'true')
os.environ.setdefault('EMBODIED_ARM_ENABLE_LOCAL_PREVIEW_COMMANDS', 'true')
