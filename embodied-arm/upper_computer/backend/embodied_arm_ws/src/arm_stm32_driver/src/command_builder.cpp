#include "arm_stm32_driver/command_builder.hpp"
namespace arm_stm32_driver { std::string CommandBuilder::build_move_j(){ return "MOVE_J"; } std::string CommandBuilder::build_home(){ return "HOME"; } std::string CommandBuilder::build_stop(){ return "STOP"; } }
