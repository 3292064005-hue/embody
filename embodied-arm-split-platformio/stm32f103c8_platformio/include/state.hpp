#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>

#include "project_config.hpp"

namespace embodied_arm::stm32fw {

struct HardwareState {
  bool home_ok{true};
  bool gripper_ok{true};
  bool gripper_open{true};
  bool motion_busy{false};
  bool limit_triggered{false};
  bool estop_pressed{false};
  int hardware_fault_code{0};
  float joint_position[kJointCount]{};
  float joint_velocity[kJointCount]{};
  String last_stage{};
  String last_kind{};
  String last_result{"idle"};
  int last_sequence{-1};
  String task_id{};

  void reset_faults() {
    limit_triggered = false;
    estop_pressed = false;
    hardware_fault_code = 0;
    last_result = "reset";
  }

  void zero_velocities() {
    for (uint8_t i = 0; i < kJointCount; ++i) {
      joint_velocity[i] = 0.0f;
    }
  }

  void to_json(JsonDocument& doc) const {
    doc["home_ok"] = home_ok;
    doc["gripper_ok"] = gripper_ok;
    doc["gripper_open"] = gripper_open;
    doc["motion_busy"] = motion_busy;
    doc["limit_triggered"] = limit_triggered;
    doc["estop_pressed"] = estop_pressed;
    doc["hardware_fault_code"] = hardware_fault_code;
    JsonArray pos = doc["joint_position"].to<JsonArray>();
    JsonArray vel = doc["joint_velocity"].to<JsonArray>();
    for (uint8_t i = 0; i < kJointCount; ++i) {
      pos.add(joint_position[i]);
      vel.add(joint_velocity[i]);
    }
    doc["last_stage"] = last_stage;
    doc["last_kind"] = last_kind;
    doc["last_result"] = last_result;
    doc["last_sequence"] = last_sequence;
    doc["task_id"] = task_id;
  }
};

}  // namespace embodied_arm::stm32fw
