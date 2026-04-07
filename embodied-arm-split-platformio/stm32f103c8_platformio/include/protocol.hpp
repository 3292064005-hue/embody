#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>

namespace embodied_arm::stm32fw {

constexpr uint8_t SOF0 = 0xAA;
constexpr uint8_t SOF1 = 0x55;
constexpr uint8_t EOF0 = 0x0D;
constexpr uint8_t EOF1 = 0x0A;

enum class HardwareCommand : uint8_t {
  HEARTBEAT = 0x01,
  HOME = 0x02,
  STOP = 0x03,
  SET_JOINTS = 0x04,
  OPEN_GRIPPER = 0x05,
  CLOSE_GRIPPER = 0x06,
  EXEC_STAGE = 0x07,
  QUERY_STATE = 0x08,
  RESET_FAULT = 0x09,
  ACK = 0x0A,
  NACK = 0x0B,
  REPORT_STATE = 0x0C,
  REPORT_FAULT = 0x0D,
};

struct FrameView {
  bool valid{false};
  uint8_t version{0};
  HardwareCommand command{HardwareCommand::QUERY_STATE};
  uint8_t sequence{0};
  String payload_json{};
  String error{};
};

uint16_t crc16_modbus(const uint8_t* data, size_t len);
FrameView decode_frame(const uint8_t* raw, size_t len);
size_t encode_frame(uint8_t version, HardwareCommand command, uint8_t sequence, const JsonDocument& payload, uint8_t* out, size_t capacity);
size_t encode_frame_from_string(uint8_t version, HardwareCommand command, uint8_t sequence, const String& payload_json, uint8_t* out, size_t capacity);

}  // namespace embodied_arm::stm32fw
