#include "arm_stm32_driver/protocol_codec.hpp"
namespace arm_stm32_driver { std::string ProtocolCodec::encode(const std::string& payload){ return payload; } bool ProtocolCodec::has_crc(uint16_t crc){ return crc != 0; } }
