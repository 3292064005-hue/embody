cmake_minimum_required(VERSION 3.8)
project(arm_stm32_driver)
find_package(ament_cmake REQUIRED)
include(CTest)
install(DIRECTORY include config src test DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  add_executable(protocol_contract_test
    test/test_protocol_contract.cpp
    src/command_builder.cpp
    src/frame_parser.cpp
    src/protocol_codec.cpp
  )
  target_include_directories(protocol_contract_test PUBLIC include)
  add_test(NAME protocol_contract_test COMMAND protocol_contract_test)
endif()

ament_package()
