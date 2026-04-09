#pragma once

#ifndef EMBODIED_ARM_WIFI_SSID
#define EMBODIED_ARM_WIFI_SSID "REPLACE_WITH_SSID"
#endif

#ifndef EMBODIED_ARM_WIFI_PASSWORD
#define EMBODIED_ARM_WIFI_PASSWORD "REPLACE_WITH_PASSWORD"
#endif

#ifndef EMBODIED_ARM_HOSTNAME
#define EMBODIED_ARM_HOSTNAME "esp32"
#endif

#include <Arduino.h>

namespace embodied_arm::esp32s3 {

static constexpr char kDefaultMode[] = "wifi";
static constexpr uint16_t kHttpPort = 80;
static constexpr char kStreamPath[] = "/stream";
static constexpr char kVoiceEventsPath[] = "/voice/events";
static constexpr char kVoicePhrasePath[] = "/voice/phrase";
static constexpr char kVoiceCommandsPath[] = "/voice/commands";
static constexpr char kHealthPath[] = "/healthz";
static constexpr char kStatusPath[] = "/status";
static constexpr uint32_t kHeartbeatPeriodMs = 1000;
static constexpr uint32_t kDisplayPeriodMs = 250;
static constexpr uint32_t kSerialPhrasePollMs = 50;
static constexpr size_t kVoiceHistoryDepth = 16;
static constexpr bool kEnableMpu6050 = true;
static constexpr bool kEnableOled = true;
static constexpr bool kEnableNeoPixel = true;
static constexpr int kI2cSdaPin = 8;
static constexpr int kI2cSclPin = 9;
static constexpr int kNeoPixelPin = 48;
static constexpr int kNeoPixelCount = 1;
static constexpr int kOledWidth = 128;
static constexpr int kOledHeight = 64;
static constexpr uint8_t kOledAddress = 0x3C;
static constexpr char kCameraSerial[] = "esp32s3-board";

}  // namespace embodied_arm::esp32s3
