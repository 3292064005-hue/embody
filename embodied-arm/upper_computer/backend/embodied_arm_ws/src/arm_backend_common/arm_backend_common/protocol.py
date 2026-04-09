from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

from .enums import HardwareCommand

SOF = b'\xAA\x55'
EOF = b'\x0D\x0A'


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            lsb = crc & 1
            crc >>= 1
            if lsb:
                crc ^= 0xA001
    return crc & 0xFFFF


@dataclass
class Frame:
    version: int
    command: int
    sequence: int
    payload: bytes

    def encode(self) -> bytes:
        body = bytes([
            self.version & 0xFF,
            self.command & 0xFF,
            self.sequence & 0xFF,
        ]) + len(self.payload).to_bytes(2, "little") + self.payload
        checksum = crc16(body).to_bytes(2, "little")
        return SOF + body + checksum + EOF

    @staticmethod
    def decode(raw: bytes) -> "Frame":
        if not raw.startswith(SOF) or not raw.endswith(EOF):
            raise ValueError("Invalid frame boundary")
        inner = raw[len(SOF):-len(EOF)]
        if len(inner) < 7:
            raise ValueError("Frame too short")
        version = inner[0]
        command = inner[1]
        sequence = inner[2]
        payload_len = int.from_bytes(inner[3:5], "little")
        expected_len = 5 + payload_len + 2
        if len(inner) != expected_len:
            raise ValueError("Payload length mismatch")
        payload = inner[5:5 + payload_len]
        checksum = int.from_bytes(inner[5 + payload_len:7 + payload_len], "little")
        if crc16(inner[:5 + payload_len]) != checksum:
            raise ValueError("CRC mismatch")
        return Frame(version=version, command=command, sequence=sequence, payload=payload)


def encode_payload(data: Dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def decode_payload(payload: bytes) -> Dict[str, Any]:
    if not payload:
        return {}
    return json.loads(payload.decode("utf-8"))


def decode_hex_frame(raw_hex: str) -> Frame:
    return Frame.decode(bytes.fromhex(raw_hex))


def build_frame(command: int | HardwareCommand, sequence: int, data: Dict[str, Any], version: int = 1) -> Frame:
    command_value = int(command.value if isinstance(command, HardwareCommand) else command)
    return Frame(version=version, command=command_value, sequence=sequence, payload=encode_payload(data))
