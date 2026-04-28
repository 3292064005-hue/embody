# Serial Protocol

> Status: generated compatibility mirror
> Canonical narrative documentation: `docs/interfaces/stm32-serial-protocol.md`
> Generator: `upper_computer/scripts/sync_doc_compatibility_mirrors.py`
> This file remains machine-readable for firmware/source contract checks and compatibility consumers. Do not replace it with a pointer page.

Use the canonical interface document for ownership, transport semantics, and integration guidance. This mirror exists because release gates still consume the legacy `docs/SERIAL_PROTOCOL.md` path.

## Frame fields
- SOF: `0xAA55`
- Command: `HardwareCommand` enum payload
- Sequence: `uint8`
- Payload: JSON string encoded by firmware/backend shared helpers
- Feedback fields: `result_code`, `execution_state`

## Command IDs
- `HEARTBEAT` = `0x01`
- `HOME` = `0x02`
- `STOP` = `0x03`
- `SET_JOINTS` = `0x04`
- `OPEN_GRIPPER` = `0x05`
- `CLOSE_GRIPPER` = `0x06`
- `EXEC_STAGE` = `0x07`
- `QUERY_STATE` = `0x08`
- `RESET_FAULT` = `0x09`
- `ACK` = `0x0A`
- `NACK` = `0x0B`
- `REPORT_STATE` = `0x0C`
- `REPORT_FAULT` = `0x0D`

## Compatibility warning
旧文档中出现过 `ESTOP / SAFE_HALT / JOG / GRIPPER`，这些名字不再作为当前权威命令字面量；兼容解释必须回落到当前 `HardwareCommand` 枚举与 canonical 文档。

## Documentation contract
- Canonical narrative path: `docs/interfaces/stm32-serial-protocol.md`
- Machine-readable mirror path: `docs/SERIAL_PROTOCOL.md`
- Firmware/backend enum drift must be fixed before this mirror can be regenerated.

