#pragma once
#include <string>
namespace arm_stm32_driver { struct CommandBuilder { static std::string build_move_j(); static std::string build_home(); static std::string build_stop(); }; }
