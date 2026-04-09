#pragma once

#include <string>
#include <unordered_map>
#include <vector>

#include "hardware_interface/system_interface.hpp"
#include "hardware_interface/types/hardware_interface_return_values.hpp"
#include "hardware_interface/types/hardware_interface_type_values.hpp"
#include "rclcpp/macros.hpp"
#include "rclcpp_lifecycle/state.hpp"

namespace arm_hardware_interface {

class EmbodiedArmSystemInterface : public hardware_interface::SystemInterface {
public:
  RCLCPP_SHARED_PTR_DEFINITIONS(EmbodiedArmSystemInterface)

  /**
   * Initialize joint bounds, default state and runtime safety parameters from
   * ros2_control hardware info. Returns ERROR when command/state interfaces do
   * not match the expected position-command + position/velocity-state contract.
   */
  hardware_interface::CallbackReturn on_init(const hardware_interface::HardwareInfo & info) override;

  /** Export independent joint position/velocity state buffers. */
  std::vector<hardware_interface::StateInterface> export_state_interfaces() override;

  /** Export clamped position command buffers consumed by controllers. */
  std::vector<hardware_interface::CommandInterface> export_command_interfaces() override;

  /** Reset the runtime state to a safe bounded position and clear stale transport markers. */
  hardware_interface::CallbackReturn on_activate(const rclcpp_lifecycle::State & previous_state) override;

  /** Stop joint motion reporting and leave the interface in a non-driving state. */
  hardware_interface::CallbackReturn on_deactivate(const rclcpp_lifecycle::State & previous_state) override;

  /**
   * Advance each joint toward its commanded target subject to position bounds,
   * configured max velocity and transport timeout. Returns ERROR on stale
   * command transport instead of silently mirroring commands to state.
   */
  hardware_interface::return_type read(const rclcpp::Time & time, const rclcpp::Duration & period) override;

  /** Clamp outbound commands and refresh the transport heartbeat timestamp. */
  hardware_interface::return_type write(const rclcpp::Time & time, const rclcpp::Duration & period) override;

private:
  double clamp_command(double value, std::size_t index) const;
  static double parse_parameter_or_default(const std::unordered_map<std::string, std::string> & parameters, const std::string & key, double fallback);

  std::vector<double> hw_positions_;
  std::vector<double> hw_velocities_;
  std::vector<double> hw_commands_;
  std::vector<double> min_positions_;
  std::vector<double> max_positions_;
  std::vector<double> max_velocities_;
  double default_position_{0.0};
  double command_timeout_sec_{0.75};
  double state_following_gain_{1.0};
  double last_write_time_sec_{-1.0};
  bool active_{false};
  bool transport_stale_{false};
};

}  // namespace arm_hardware_interface
