#pragma once

#include <Arduino.h>
#include <vector>

namespace embodied_arm::esp32s3 {

struct VoiceEvent {
  String phrase;
  String source;
  uint32_t stamp_ms{0};
};

struct BoardState {
  bool online{true};
  bool wifi_connected{false};
  bool camera_available{false};
  bool imu_available{false};
  bool display_available{false};
  bool led_available{false};
  String mode{"wifi"};
  String stream_endpoint{"http://esp32.local/stream"};
  String hostname{"esp32"};
  String ip_address{"0.0.0.0"};
  String camera_serial{"esp32s3-board"};
  int32_t wifi_rssi{0};
  uint32_t heartbeat_counter{0};
  uint32_t uptime_ms{0};
  float accel_x{0.0f};
  float accel_y{0.0f};
  float accel_z{0.0f};
  float gyro_x{0.0f};
  float gyro_y{0.0f};
  float gyro_z{0.0f};
  std::vector<VoiceEvent> voice_history{};
};

}  // namespace embodied_arm::esp32s3
