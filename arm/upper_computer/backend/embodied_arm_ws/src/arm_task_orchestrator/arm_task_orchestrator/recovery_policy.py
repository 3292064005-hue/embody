from __future__ import annotations


class RecoveryPolicy:
    def decide(self, fault_code: int) -> dict:
        if int(fault_code) == 0:
            return {'action': 'noop'}
        return {'action': 'recover', 'fault_code': int(fault_code)}
