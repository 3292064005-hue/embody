#include <cassert>
#include <string>
#include <vector>

#include "arm_stm32_driver/command_builder.hpp"
#include "arm_stm32_driver/frame_parser.hpp"
#include "arm_stm32_driver/protocol_codec.hpp"

int main() {
  using namespace arm_stm32_driver;

  assert(CommandBuilder::build_home() == "HOME");
  assert(CommandBuilder::build_move_j() == "MOVE_J");
  assert(CommandBuilder::build_stop() == "STOP");

  const std::string payload = R"({\"kind\":\"QUERY_STATE\"})";
  const std::string encoded = ProtocolCodec::encode(payload);
  assert(encoded == payload);
  assert(ProtocolCodec::has_crc(0x0001));
  assert(!ProtocolCodec::has_crc(0x0000));

  FrameParser parser;
  const std::vector<std::string> frames = parser.feed(encoded);
  assert(frames.size() == 1);
  assert(frames.front() == encoded);

  return 0;
}
