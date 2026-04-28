#pragma once
#include <string>
#include <vector>
namespace arm_stm32_driver { struct FrameParser { std::vector<std::string> feed(const std::string& chunk); }; }
