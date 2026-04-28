#pragma once
#include <string>
namespace arm_stm32_driver { struct SerialPort { std::string port; int baudrate{115200}; }; }
