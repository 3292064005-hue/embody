#include <Arduino.h>
#include <ArduinoJson.h>
#include <math.h>
#include <string.h>

#include "project_config.hpp"
#include "protocol.hpp"
#include "state.hpp"

using embodied_arm::stm32fw::FrameView;
using embodied_arm::stm32fw::HardwareCommand;
using embodied_arm::stm32fw::HardwareState;

namespace {
using namespace embodied_arm::stm32fw;

struct ScheduledFrame {
  bool active{false};
  uint32_t due_ms{0};
  HardwareCommand command{HardwareCommand::REPORT_STATE};
  uint8_t sequence{0};
  String payload_json{};
};

struct RecentCommand {
  bool active{false};
  uint8_t sequence{0};
  uint8_t command{0};
  uint32_t seen_ms{0};
};

HardwareSerial& transport = Serial1;
HardwareState state{};
ScheduledFrame report_queue[kReportQueueDepth];
RecentCommand dedupe[kRecentCommandDepth];
uint8_t rx_buffer[320]{};
size_t rx_len = 0;
uint32_t last_periodic_report_ms = 0;
uint32_t last_host_contact_ms = 0;

String jsonString(const JsonDocument& doc) {
  String out;
  serializeJson(doc, out);
  return out;
}

void setLed(bool on) {
  digitalWrite(kLedPin, on ? LOW : HIGH);
}

bool readActiveLow(uint8_t pin) {
  return digitalRead(pin) == LOW;
}

void sendFrame(HardwareCommand command, uint8_t sequence, const JsonDocument& payload) {
  uint8_t out[300]{};
  const size_t used = encode_frame(1, command, sequence, payload, out, sizeof(out));
  if (used > 0) {
    transport.write(out, used);
  }
}

void sendFrameString(HardwareCommand command, uint8_t sequence, const String& payload) {
  uint8_t out[300]{};
  const size_t used = encode_frame_from_string(1, command, sequence, payload, out, sizeof(out));
  if (used > 0) {
    transport.write(out, used);
  }
}

void queueReport(HardwareCommand command, uint8_t sequence, const String& payload_json, uint32_t delay_ms) {
  for (auto& item : report_queue) {
    if (!item.active) {
      item.active = true;
      item.due_ms = millis() + delay_ms;
      item.command = command;
      item.sequence = sequence;
      item.payload_json = payload_json;
      return;
    }
  }
}

void scheduleStateReport(uint8_t sequence, uint32_t delay_ms) {
  StaticJsonDocument<320> doc;
  state.to_json(doc);
  doc["result_code"] = state.result_code;
  doc["execution_state"] = state.execution_state;
  queueReport(HardwareCommand::REPORT_STATE, sequence, jsonString(doc), delay_ms);
}

void scheduleFaultReport(uint8_t sequence, const char* message, uint32_t delay_ms) {
  StaticJsonDocument<224> doc;
  doc["hardware_fault_code"] = state.hardware_fault_code;
  doc["message"] = message;
  doc["task_id"] = state.task_id;
  doc["transport_state"] = state.transport_state.length() > 0 ? state.transport_state : String("accepted");
  doc["transport_result"] = state.transport_result.length() > 0 ? state.transport_result : String("accepted");
  doc["actuation_state"] = "fault";
  doc["actuation_result"] = state.actuation_result.length() > 0 ? state.actuation_result : String(state.hardware_fault_code);
  doc["result_code"] = state.result_code.length() > 0 ? state.result_code : String(state.hardware_fault_code);
  doc["execution_state"] = "fault";
  queueReport(HardwareCommand::REPORT_FAULT, sequence, jsonString(doc), delay_ms);
}

void sendAck(uint8_t sequence, uint8_t command) {
  StaticJsonDocument<128> doc;
  doc["ack_sequence"] = sequence;
  doc["command"] = command;
  doc["ok"] = true;
  doc["transport_state"] = "accepted";
  doc["transport_result"] = "accepted";
  doc["actuation_state"] = "pending";
  doc["actuation_result"] = "accepted";
  doc["result_code"] = "accepted";
  doc["execution_state"] = "pending";
  sendFrame(HardwareCommand::ACK, sequence, doc);
}

void sendNack(uint8_t sequence, const char* message) {
  StaticJsonDocument<160> doc;
  doc["ack_sequence"] = sequence;
  doc["message"] = message;
  doc["transport_state"] = "rejected";
  doc["transport_result"] = "rejected";
  doc["actuation_state"] = "failed";
  doc["actuation_result"] = "rejected";
  doc["result_code"] = "rejected";
  doc["execution_state"] = "failed";
  sendFrame(HardwareCommand::NACK, sequence, doc);
}

void clearInputNoise() {
  while (rx_len >= 2 && !(rx_buffer[0] == SOF0 && rx_buffer[1] == SOF1)) {
    memmove(rx_buffer, rx_buffer + 1, --rx_len);
  }
}

bool isDuplicate(uint8_t sequence, uint8_t command) {
  const uint32_t now = millis();
  for (const auto& entry : dedupe) {
    if (!entry.active) {
      continue;
    }
    if (entry.sequence == sequence && entry.command == command && (now - entry.seen_ms) <= kDedupeWindowMs) {
      return true;
    }
  }
  return false;
}

void rememberCommand(uint8_t sequence, uint8_t command) {
  const uint32_t now = millis();
  for (auto& entry : dedupe) {
    if (!entry.active) {
      entry.active = true;
      entry.sequence = sequence;
      entry.command = command;
      entry.seen_ms = now;
      return;
    }
  }
  for (uint8_t i = 1; i < kRecentCommandDepth; ++i) {
    dedupe[i - 1] = dedupe[i];
  }
  dedupe[kRecentCommandDepth - 1] = {true, sequence, command, now};
}

String getString(JsonVariantConst value, const char* fallback = "") {
  if (value.is<const char*>()) {
    return String(value.as<const char*>());
  }
  if (value.is<String>()) {
    return value.as<String>();
  }
  return String(fallback);
}

float getFloat(JsonVariantConst value, float fallback = 0.0f) {
  if (value.is<float>() || value.is<double>() || value.is<int>() || value.is<long>()) {
    return value.as<float>();
  }
  return fallback;
}

int getInt(JsonVariantConst value, int fallback = 0) {
  if (value.is<int>() || value.is<long>() || value.is<float>() || value.is<double>()) {
    return value.as<int>();
  }
  return fallback;
}

void applyExecStage(const JsonDocument& payload) {
  const JsonObjectConst pose = payload["pose"].as<JsonObjectConst>();
  const float x = pose.isNull() ? getFloat(payload["x"], state.joint_position[0]) : getFloat(pose["x"], state.joint_position[0]);
  const float y = pose.isNull() ? getFloat(payload["y"], state.joint_position[1]) : getFloat(pose["y"], state.joint_position[1]);
  const float z = pose.isNull() ? getFloat(payload["z"], state.joint_position[2]) : getFloat(pose["z"], state.joint_position[2]);
  const float yaw = pose.isNull() ? getFloat(payload["yaw"], state.joint_position[3]) : getFloat(pose["yaw"], state.joint_position[3]);
  state.joint_velocity[0] = fabsf(x - state.joint_position[0]);
  state.joint_velocity[1] = fabsf(y - state.joint_position[1]);
  state.joint_velocity[2] = fabsf(z - state.joint_position[2]);
  state.joint_velocity[3] = fabsf(yaw - state.joint_position[3]);
  state.joint_position[0] = x;
  state.joint_position[1] = y;
  state.joint_position[2] = z;
  state.joint_position[3] = yaw;
  state.motion_busy = false;
  state.last_result = "done";
  state.transport_state = "completed";
  state.transport_result = "accepted";
  state.actuation_state = "succeeded";
  state.actuation_result = "stage_completed";
  state.result_code = state.actuation_result;
  state.execution_state = state.actuation_state;
}

void applyJogJoint(const JsonDocument& payload) {
  const int joint_index = constrain(getInt(payload["jointIndex"], 0), 0, kJointCount - 1);
  const int direction = getInt(payload["direction"], 1) >= 0 ? 1 : -1;
  const float step_deg = getFloat(payload["stepDeg"], 0.0f);
  const float step_rad = direction * (step_deg * 3.14159265358979323846f / 180.0f);
  state.joint_position[joint_index] += step_rad;
  state.joint_velocity[joint_index] = fabsf(step_rad);
  state.motion_busy = false;
  state.last_result = "jogged";
  state.transport_state = "completed";
  state.transport_result = "accepted";
  state.actuation_state = "succeeded";
  state.actuation_result = "joint_jogged";
  state.result_code = state.actuation_result;
  state.execution_state = state.actuation_state;
}

void applyServoCartesian(const JsonDocument& payload) {
  const String axis = getString(payload["axis"], "x");
  const float delta = getFloat(payload["delta"], 0.0f);
  int joint_index = 0;
  if (axis == "y") joint_index = 1;
  else if (axis == "z") joint_index = 2;
  else if (axis == "rx") joint_index = 3;
  else if (axis == "ry") joint_index = 4;
  state.joint_position[joint_index] += delta;
  state.joint_velocity[joint_index] = fabsf(delta);
  state.motion_busy = false;
  state.last_result = String("servo_") + axis;
  state.transport_state = "completed";
  state.transport_result = "accepted";
  state.actuation_state = "succeeded";
  state.actuation_result = String("servo_") + axis;
  state.result_code = state.actuation_result;
  state.execution_state = state.actuation_state;
}

void updateSafetyPins() {
  const bool estop = kUseEstopPin ? readActiveLow(kEstopPin) : false;
  const bool limit = kUseLimitPin ? readActiveLow(kLimitPin) : false;

  if (estop && !state.estop_pressed) {
    state.estop_pressed = true;
    state.hardware_fault_code = 4004;
    state.motion_busy = false;
    state.last_result = "estop";
    state.transport_state = "completed";
    state.transport_result = "accepted";
    state.actuation_state = "fault";
    state.actuation_result = "estop_pressed";
    state.result_code = state.actuation_result;
    state.execution_state = state.actuation_state;
    scheduleFaultReport(static_cast<uint8_t>(state.last_sequence < 0 ? 0 : state.last_sequence), "Emergency stop pressed", 5);
  }
  if (limit && !state.limit_triggered) {
    state.limit_triggered = true;
    state.hardware_fault_code = 4002;
    state.motion_busy = false;
    state.last_result = "limit_triggered";
    state.transport_state = "completed";
    state.transport_result = "accepted";
    state.actuation_state = "fault";
    state.actuation_result = "limit_triggered";
    state.result_code = state.actuation_result;
    state.execution_state = state.actuation_state;
    scheduleFaultReport(static_cast<uint8_t>(state.last_sequence < 0 ? 0 : state.last_sequence), "Limit triggered", 5);
  }
}

void processCommand(const FrameView& frame) {
  StaticJsonDocument<256> payload;
  if (frame.payload_json.length() > 0) {
    const DeserializationError err = deserializeJson(payload, frame.payload_json);
    if (err) {
      sendNack(frame.sequence, "invalid json payload");
      return;
    }
  }

  const String kind = getString(payload["kind"], "");
  const String stage = getString(payload["stage"], "");
  const String task_id = getString(payload["task_id"], "");
  state.last_sequence = frame.sequence;
  state.last_kind = kind.length() > 0 ? kind : String(static_cast<int>(frame.command));
  state.last_stage = stage;
  state.task_id = task_id;
  state.zero_velocities();
  state.transport_state = "accepted";
  state.transport_result = "accepted";
  state.actuation_state = "pending";
  state.actuation_result = "accepted";
  state.execution_state = state.actuation_state;
  state.result_code = state.actuation_result;
  last_host_contact_ms = millis();

  switch (frame.command) {
    case HardwareCommand::HEARTBEAT:
      sendAck(frame.sequence, static_cast<uint8_t>(frame.command));
      state.last_result = "heartbeat";
      state.transport_state = "completed";
      state.transport_result = "accepted";
      state.actuation_state = "succeeded";
      state.actuation_result = "heartbeat";
      state.result_code = state.actuation_result;
      state.execution_state = state.actuation_state;
      scheduleStateReport(frame.sequence, 10);
      return;
    case HardwareCommand::HOME:
      sendAck(frame.sequence, static_cast<uint8_t>(frame.command));
      state.home_ok = true;
      state.motion_busy = false;
      for (uint8_t i = 0; i < kJointCount; ++i) state.joint_position[i] = 0.0f;
      state.last_result = "home_ok";
      state.transport_state = "completed";
      state.transport_result = "accepted";
      state.actuation_state = "succeeded";
      state.actuation_result = "homed";
      state.result_code = state.actuation_result;
      state.execution_state = state.actuation_state;
      scheduleStateReport(frame.sequence, 120);
      return;
    case HardwareCommand::STOP:
      sendAck(frame.sequence, static_cast<uint8_t>(frame.command));
      state.motion_busy = false;
      state.last_result = "stopped";
      state.transport_state = "completed";
      state.transport_result = "accepted";
      state.actuation_state = "canceled";
      state.actuation_result = "stopped";
      state.result_code = state.actuation_result;
      state.execution_state = state.actuation_state;
      scheduleStateReport(frame.sequence, 30);
      return;
    case HardwareCommand::OPEN_GRIPPER:
      sendAck(frame.sequence, static_cast<uint8_t>(frame.command));
      state.gripper_ok = true;
      state.gripper_open = true;
      state.motion_busy = false;
      state.last_result = "opened";
      state.transport_state = "completed";
      state.transport_result = "accepted";
      state.actuation_state = "succeeded";
      state.actuation_result = "gripper_open";
      state.result_code = state.actuation_result;
      state.execution_state = state.actuation_state;
      scheduleStateReport(frame.sequence, 60);
      return;
    case HardwareCommand::CLOSE_GRIPPER:
      sendAck(frame.sequence, static_cast<uint8_t>(frame.command));
      state.gripper_ok = true;
      state.gripper_open = false;
      state.motion_busy = false;
      state.last_result = "closed";
      state.transport_state = "completed";
      state.transport_result = "accepted";
      state.actuation_state = "succeeded";
      state.actuation_result = "gripper_closed";
      state.result_code = state.actuation_result;
      state.execution_state = state.actuation_state;
      scheduleStateReport(frame.sequence, 60);
      return;
    case HardwareCommand::EXEC_STAGE:
      sendAck(frame.sequence, static_cast<uint8_t>(frame.command));
      state.motion_busy = true;
      state.transport_state = "accepted";
      state.transport_result = "accepted";
      state.actuation_state = "executing";
      state.actuation_result = "executing_stage";
      state.execution_state = state.actuation_state;
      state.result_code = state.actuation_result;
      applyExecStage(payload);
      scheduleStateReport(frame.sequence, 100);
      return;
    case HardwareCommand::QUERY_STATE:
      sendAck(frame.sequence, static_cast<uint8_t>(frame.command));
      state.last_result = "state";
      state.transport_state = "completed";
      state.transport_result = "accepted";
      state.actuation_state = "succeeded";
      state.actuation_result = "state_snapshot";
      state.result_code = state.actuation_result;
      state.execution_state = state.actuation_state;
      scheduleStateReport(frame.sequence, 10);
      return;
    case HardwareCommand::RESET_FAULT:
      sendAck(frame.sequence, static_cast<uint8_t>(frame.command));
      state.reset_faults();
      scheduleStateReport(frame.sequence, 50);
      return;
    case HardwareCommand::SET_JOINTS:
      sendAck(frame.sequence, static_cast<uint8_t>(frame.command));
      state.motion_busy = true;
      if (kind == "JOG_JOINT") {
        applyJogJoint(payload);
      } else if (kind == "SERVO_CARTESIAN") {
        applyServoCartesian(payload);
      } else {
        state.motion_busy = false;
        state.last_result = "set_joints";
        state.transport_state = "completed";
        state.transport_result = "accepted";
        state.actuation_state = "succeeded";
        state.actuation_result = "joint_positions_applied";
        state.result_code = state.actuation_result;
        state.execution_state = state.actuation_state;
      }
      scheduleStateReport(frame.sequence, 40);
      return;
    default:
      sendNack(frame.sequence, "unsupported command");
      state.last_result = "unsupported";
      state.transport_state = "rejected";
      state.transport_result = "unsupported_command";
      state.actuation_state = "failed";
      state.actuation_result = "unsupported_command";
      state.result_code = state.actuation_result;
      state.execution_state = state.actuation_state;
      return;
  }
}

void processSerial() {
  while (transport.available() > 0 && rx_len < sizeof(rx_buffer)) {
    rx_buffer[rx_len++] = static_cast<uint8_t>(transport.read());
  }

  clearInputNoise();
  while (rx_len >= 11) {
    const uint16_t payload_len = static_cast<uint16_t>(rx_buffer[5]) | (static_cast<uint16_t>(rx_buffer[6]) << 8U);
    const size_t frame_len = 2 + 1 + 1 + 1 + 2 + payload_len + 2 + 2;
    if (frame_len > sizeof(rx_buffer)) {
      rx_len = 0;
      return;
    }
    if (rx_len < frame_len) {
      return;
    }
    FrameView frame = decode_frame(rx_buffer, frame_len);
    memmove(rx_buffer, rx_buffer + frame_len, rx_len - frame_len);
    rx_len -= frame_len;
    clearInputNoise();

    if (!frame.valid) {
      continue;
    }
    if (isDuplicate(frame.sequence, static_cast<uint8_t>(frame.command))) {
      sendAck(frame.sequence, static_cast<uint8_t>(frame.command));
      scheduleStateReport(frame.sequence, 10);
      continue;
    }
    rememberCommand(frame.sequence, static_cast<uint8_t>(frame.command));
    processCommand(frame);
  }
}

void flushScheduledFrames() {
  const uint32_t now = millis();
  for (auto& item : report_queue) {
    if (!item.active || now < item.due_ms) {
      continue;
    }
    sendFrameString(item.command, item.sequence, item.payload_json);
    item.active = false;
    item.payload_json = String();
  }
}

void maybePeriodicStateReport() {
  const uint32_t now = millis();
  if (now - last_periodic_report_ms < kPeriodicReportMs) {
    return;
  }
  last_periodic_report_ms = now;
  scheduleStateReport(static_cast<uint8_t>(state.last_sequence < 0 ? 0 : state.last_sequence), 5);
}

}  // namespace

void setup() {
  pinMode(kLedPin, OUTPUT);
  setLed(true);
  if (kUseEstopPin) {
    pinMode(kEstopPin, INPUT_PULLUP);
  }
  if (kUseLimitPin) {
    pinMode(kLimitPin, INPUT_PULLUP);
  }

  Serial.begin(kSerialBaud);
  transport.begin(kSerialBaud);
  state.home_ok = true;
  state.gripper_ok = true;
  state.gripper_open = true;
  last_host_contact_ms = millis();
}

void loop() {
  updateSafetyPins();
  processSerial();
  maybePeriodicStateReport();
  flushScheduledFrames();
  setLed((millis() / 250U) % 2U == 0U);
}
