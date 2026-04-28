from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    path = Path('artifacts/hil/hil_checklist.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'status': 'pending',
        'failurePathCoverage': {
            'automaticSubset': 'pending',
            'hil': 'pending',
        },
        'items': [
            {'name': 'runtime_real.launch smoke', 'status': 'pending', 'owner': 'ros2'},
            {'name': 'dispatcher round-trip', 'status': 'pending', 'owner': 'ros2/gateway'},
            {'name': 'manual control safety chain', 'status': 'pending', 'owner': 'ros2/gateway/ui'},
            {'name': 'estop / reset / recover', 'status': 'pending', 'owner': 'ros2/gateway/ui'},
            {'name': 'negative-path subset: hardware bridge unavailable', 'status': 'pending', 'owner': 'ros2'},
            {'name': 'negative-path subset: readiness blocked propagation', 'status': 'pending', 'owner': 'gateway/ui'},
            {'name': 'negative-path subset: safety stop propagation', 'status': 'pending', 'owner': 'ros2/gateway/ui'},
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(path)


if __name__ == '__main__':
    main()
