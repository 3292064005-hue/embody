from __future__ import annotations

import os

# Most gateway integration tests exercise the explicit local HMI development
# profile rather than the default fail-closed target-runtime profile.
os.environ.setdefault('EMBODIED_ARM_RUNTIME_PROFILE', 'dev-hmi-mock')
os.environ.setdefault('EMBODIED_ARM_ALLOW_SIMULATION_FALLBACK', 'true')
