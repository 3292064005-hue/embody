#include "protocol.hpp"

namespace embodied_arm::stm32fw {

uint16_t crc16_modbus(const uint8_t* data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      const bool lsb = (crc & 0x0001U) != 0;
      crc >>= 1U;
      if (lsb) {
        crc ^= 0xA001U;
      }
    }
  }
  return crc;
}

FrameView decode_frame(const uint8_t* raw, size_t len) {
  FrameView view{};
  if (len < 11) {
    view.error = "frame too short";
    return view;
  }
  if (raw[0] != SOF0 || raw[1] != SOF1 || raw[len - 2] != EOF0 || raw[len - 1] != EOF1) {
    view.error = "invalid frame boundary";
    return view;
  }
  const uint8_t version = raw[2];
  const uint8_t command = raw[3];
  const uint8_t sequence = raw[4];
  const uint16_t payload_len = static_cast<uint16_t>(raw[5]) | (static_cast<uint16_t>(raw[6]) << 8U);
  const size_t expected = static_cast<size_t>(2 + 1 + 1 + 1 + 2 + payload_len + 2 + 2);
  if (len != expected) {
    view.error = "payload length mismatch";
    return view;
  }
  const size_t body_len = 1 + 1 + 1 + 2 + payload_len;
  const uint8_t* body = raw + 2;
  const uint16_t checksum = static_cast<uint16_t>(raw[7 + payload_len]) | (static_cast<uint16_t>(raw[8 + payload_len]) << 8U);
  if (crc16_modbus(body, body_len) != checksum) {
    view.error = "crc mismatch";
    return view;
  }
  view.valid = true;
  view.version = version;
  view.command = static_cast<HardwareCommand>(command);
  view.sequence = sequence;
  if (payload_len > 0) {
    view.payload_json.reserve(payload_len);
    for (size_t i = 0; i < payload_len; ++i) {
      view.payload_json += static_cast<char>(raw[7 + i]);
    }
  }
  return view;
}

size_t encode_frame_from_string(uint8_t version, HardwareCommand command, uint8_t sequence, const String& payload_json, uint8_t* out, size_t capacity) {
  const size_t payload_len = payload_json.length();
  const size_t total = 2 + 1 + 1 + 1 + 2 + payload_len + 2 + 2;
  if (capacity < total) {
    return 0;
  }

  out[0] = SOF0;
  out[1] = SOF1;
  out[2] = version;
  out[3] = static_cast<uint8_t>(command);
  out[4] = sequence;
  out[5] = static_cast<uint8_t>(payload_len & 0xFFU);
  out[6] = static_cast<uint8_t>((payload_len >> 8U) & 0xFFU);
  for (size_t i = 0; i < payload_len; ++i) {
    out[7 + i] = static_cast<uint8_t>(payload_json[i]);
  }
  const uint16_t crc = crc16_modbus(out + 2, 5 + payload_len);
  out[7 + payload_len] = static_cast<uint8_t>(crc & 0xFFU);
  out[8 + payload_len] = static_cast<uint8_t>((crc >> 8U) & 0xFFU);
  out[9 + payload_len] = EOF0;
  out[10 + payload_len] = EOF1;
  return total;
}

size_t encode_frame(uint8_t version, HardwareCommand command, uint8_t sequence, const JsonDocument& payload, uint8_t* out, size_t capacity) {
  String payload_json;
  serializeJson(payload, payload_json);
  return encode_frame_from_string(version, command, sequence, payload_json, out, capacity);
}

}  // namespace embodied_arm::stm32fw
