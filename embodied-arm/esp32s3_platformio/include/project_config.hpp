#pragma once

#ifndef EMBODIED_ARM_WIFI_SSID
#define EMBODIED_ARM_WIFI_SSID "REPLACE_WITH_SSID"
#endif

#ifndef EMBODIED_ARM_WIFI_PASSWORD
#define EMBODIED_ARM_WIFI_PASSWORD "REPLACE_WITH_PASSWORD"
#endif

#include <Arduino.h>
#include "generated/runtime_semantic_profile.hpp"

#ifndef EMBODIED_ARM_HOSTNAME
#define EMBODIED_ARM_HOSTNAME EMBODIED_ARM_DEFAULT_HOSTNAME
#endif

#ifndef EMBODIED_ARM_CAMERA_AVAILABLE
#define EMBODIED_ARM_CAMERA_AVAILABLE EMBODIED_ARM_DEFAULT_CAMERA_AVAILABLE
#endif

#ifndef EMBODIED_ARM_FRAME_INGRESS_LIVE
#define EMBODIED_ARM_FRAME_INGRESS_LIVE EMBODIED_ARM_DEFAULT_FRAME_INGRESS_LIVE
#endif

#ifndef EMBODIED_ARM_STREAM_SEMANTIC
#define EMBODIED_ARM_STREAM_SEMANTIC EMBODIED_ARM_DEFAULT_STREAM_SEMANTIC
#endif

#ifndef EMBODIED_ARM_FRAME_INGRESS_MODE
#define EMBODIED_ARM_FRAME_INGRESS_MODE EMBODIED_ARM_DEFAULT_FRAME_INGRESS_MODE
#endif

#ifndef EMBODIED_ARM_STREAM_DELIVERY_MODEL
#define EMBODIED_ARM_STREAM_DELIVERY_MODEL EMBODIED_ARM_DEFAULT_STREAM_DELIVERY_MODEL
#endif

#ifndef EMBODIED_ARM_STREAM_CONTROL_PLANE
#define EMBODIED_ARM_STREAM_CONTROL_PLANE EMBODIED_ARM_DEFAULT_STREAM_CONTROL_PLANE
#endif

#ifndef EMBODIED_ARM_STREAM_MESSAGE
#define EMBODIED_ARM_STREAM_MESSAGE EMBODIED_ARM_DEFAULT_STREAM_MESSAGE
#endif

namespace embodied_arm::esp32s3 {

static constexpr char kDefaultMode[] = "wifi";
static constexpr char kRuntimeSemanticProfile[] = EMBODIED_ARM_RUNTIME_SEMANTIC_PROFILE_NAME;
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
static constexpr char kSourceLane[] = EMBODIED_ARM_DEFAULT_SOURCE_LANE;
static constexpr bool kCameraAvailable = EMBODIED_ARM_CAMERA_AVAILABLE != 0;
static constexpr bool kFrameIngressLive = EMBODIED_ARM_FRAME_INGRESS_LIVE != 0;
static constexpr char kStreamSemantic[] = EMBODIED_ARM_STREAM_SEMANTIC;
static constexpr char kFrameIngressMode[] = EMBODIED_ARM_FRAME_INGRESS_MODE;
static constexpr char kStreamDeliveryModel[] = EMBODIED_ARM_STREAM_DELIVERY_MODEL;
static constexpr char kStreamControlPlane[] = EMBODIED_ARM_STREAM_CONTROL_PLANE;
static constexpr char kStreamMessage[] = EMBODIED_ARM_STREAM_MESSAGE;

}  // namespace embodied_arm::esp32s3
