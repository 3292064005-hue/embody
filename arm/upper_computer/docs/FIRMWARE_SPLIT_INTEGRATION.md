# Firmware Split Integration

> Status: generated compatibility mirror
> Canonical narrative documentation: `docs/operations/firmware-integration.md`
> Generator: `upper_computer/scripts/sync_doc_compatibility_mirrors.py`
> This file remains machine-readable for split repository checks and legacy consumers. Do not replace it with a pointer page.

Use the canonical operations document for ownership, rollout order, and narrative integration guidance. This mirror exists because release gates still consume the legacy `docs/FIRMWARE_SPLIT_INTEGRATION.md` path.

## Canonical source mapping
- canonical document: `docs/operations/firmware-integration.md`
- split verification script: `scripts/verify_firmware_sources.py`

## ESP32 HTTP route contract
- `kStreamPath` → `/stream`
- `kVoiceEventsPath` → `/voice/events`
- `kVoicePhrasePath` → `/voice/phrase`
- `kVoiceCommandsPath` → `/voice/commands`
- `kHealthPath` → `/healthz`
- `kStatusPath` → `/status`

## Split responsibilities
- ESP32-S3: Wi-Fi / endpoint reachability / board health / metadata bridge / voice-observability ingress
- STM32F103C8: serial protocol / ACK-NACK / state and fault reporting / dispatcher-facing execution transport

## Integration chain
`gateway -> ROS2 backend -> dispatcher / bridge -> firmware protocol / transport -> firmware`

## Documentation contract
- Legacy path remains a generated compatibility mirror.
- Canonical prose and ownership stay in `docs/operations/firmware-integration.md`.
- Route additions or removals must update firmware code and regenerate this mirror in the same change.

