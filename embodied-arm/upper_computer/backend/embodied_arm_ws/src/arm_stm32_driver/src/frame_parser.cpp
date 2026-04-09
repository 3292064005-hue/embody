#include "arm_stm32_driver/frame_parser.hpp"
namespace arm_stm32_driver { std::vector<std::string> FrameParser::feed(const std::string& chunk){ return chunk.empty() ? std::vector<std::string>{} : std::vector<std::string>{chunk}; } }
