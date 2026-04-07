#pragma once

#ifndef EMBODIED_ARM_UART_BAUD
#define EMBODIED_ARM_UART_BAUD 115200
#endif

#include <Arduino.h>

namespace embodied_arm::stm32fw {

static constexpr uint32_t kSerialBaud = EMBODIED_ARM_UART_BAUD;
static constexpr uint32_t kPeriodicReportMs = 500;
static constexpr uint32_t kDedupeWindowMs = 800;
static constexpr uint8_t kMaxFramePayload = 220;
static constexpr uint8_t kRecentCommandDepth = 8;
static constexpr uint8_t kReportQueueDepth = 4;
static constexpr uint8_t kJointCount = 5;
static constexpr uint8_t kLedPin = PC13;
static constexpr uint8_t kEstopPin = PB12;
static constexpr uint8_t kLimitPin = PB13;
static constexpr bool kUseEstopPin = true;
static constexpr bool kUseLimitPin = true;

}  // namespace embodied_arm::stm32fw
