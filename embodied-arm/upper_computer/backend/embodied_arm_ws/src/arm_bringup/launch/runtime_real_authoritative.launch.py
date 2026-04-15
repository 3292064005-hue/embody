"""Retired compatibility wrapper for the historic real_authoritative entry.

This wrapper intentionally resolves through the retired alias name so the
default retirement guard in ``launch_factory`` still applies. Operators must
either use the canonical experimental lane (``live_control``) /
``experimental_*`` aliases, or set
``EMBODIED_ARM_ALLOW_LEGACY_LIVE_ALIASES=true`` for a temporary migration
window.
"""

from arm_bringup.launch_factory import build_runtime_launch_description


def generate_launch_description():
    return build_runtime_launch_description('real_authoritative')
