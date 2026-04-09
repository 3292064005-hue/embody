#pragma once
#include <cstdint>
#include <string>
namespace arm_stm32_driver { struct ProtocolCodec { static std::string encode(const std::string& payload); static bool has_crc(uint16_t crc); }; }
