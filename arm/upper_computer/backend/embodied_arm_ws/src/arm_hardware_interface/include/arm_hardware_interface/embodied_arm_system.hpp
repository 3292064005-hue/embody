#pragma once

#include <atomic>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include "hardware_interface/system_interface.hpp"
#include "hardware_interface/types/hardware_interface_return_values.hpp"
#include "hardware_interface/types/hardware_interface_type_values.hpp"
#include "rclcpp/executors/single_threaded_executor.hpp"
#include "rclcpp/macros.hpp"
#include "rclcpp/node.hpp"
#include "rclcpp_lifecycle/state.hpp"
#include "std_msgs/msg/string.hpp"
#include "arm_interfaces/msg/hardware_state.hpp"

namespace arm_hardware_interface {

class EmbodiedArmSystemInterface : public hardware_interface::SystemInterface {
public:
  RCLCPP_SHARED_PTR_DEFINITIONS(EmbodiedArmSystemInterface)

  /**
   * Initialize joint bounds, transport contracts, and optional ROS bridge
   * parameters from ros2_control hardware info.
   *
   * Functional behavior:
   *   - validates the exported position-command/state interface contract
   *   - loads joint limits and command timeouts
   *   - resolves whether runtime state comes from local shadow following or the
   *     aggregated hardware-state topic
   *
   * Returns:
   *   SUCCESS when the hardware contract is structurally valid.
   *
   * Raises:
   *   Does not raise. Invalid configurations return ERROR.
   */
  hardware_interface::CallbackReturn on_init(const hardware_interface::HardwareInfo & info) override;

  /** Export independent joint position/velocity state buffers. */
  std::vector<hardware_interface::StateInterface> export_state_interfaces() override;

  /** Export clamped position command buffers consumed by controllers. */
  std::vector<hardware_interface::CommandInterface> export_command_interfaces() override;

  /**
   * Reset the runtime state and start the optional ROS topic bridge when the
   * configured state source depends on external hardware feedback.
   */
  hardware_interface::CallbackReturn on_activate(const rclcpp_lifecycle::State & previous_state) override;

  /** Stop the optional ROS topic bridge and leave the interface non-driving. */
  hardware_interface::CallbackReturn on_deactivate(const rclcpp_lifecycle::State & previous_state) override;

  /**
   * Refresh controller-visible state.
   *
   * Boundary behavior:
   *   - shadow_following mode advances state toward commands for fake hardware
   *   - external_feedback mode fails closed when feedback becomes stale,
   *     transport drops offline, or the aggregated hardware state reports a
   *     fault
   */
  hardware_interface::return_type read(const rclcpp::Time & time, const rclcpp::Duration & period) override;

  /**
   * Clamp outbound commands and publish them onto the authoritative hardware
   * command topic when the interface is configured for external feedback.
   */
  hardware_interface::return_type write(const rclcpp::Time & time, const rclcpp::Duration & period) override;

private:
  enum class StateSourceMode {
    ShadowFollowing,
    ExternalFeedback,
  };

  double clamp_command(double value, std::size_t index) const;
  static double parse_parameter_or_default(const std::unordered_map<std::string, std::string> & parameters, const std::string & key, double fallback);
  static bool parse_bool_parameter_or_default(const std::unordered_map<std::string, std::string> & parameters, const std::string & key, bool fallback);
  static std::string parse_string_parameter_or_default(const std::unordered_map<std::string, std::string> & parameters, const std::string & key, const std::string & fallback);
  static StateSourceMode parse_state_source_mode(const std::unordered_map<std::string, std::string> & parameters);
  static bool extract_gripper_open_from_raw_status(const std::string & raw_status, bool fallback);
  static bool extract_named_bool_from_raw_status(const std::string & raw_status, const std::string & key, bool fallback);

  void ensure_ros_bridge_started();
  void shutdown_ros_bridge();
  void handle_hardware_state(const arm_interfaces::msg::HardwareState::SharedPtr msg);
  bool command_publish_due(double now_sec) const;
  bool command_changed() const;
  std::string build_set_joints_command_json() const;
  std::vector<std::string> arm_joint_names() const;

  mutable std::mutex state_mutex_;
  std::vector<double> hw_positions_;
  std::vector<double> hw_velocities_;
  std::vector<double> hw_commands_;
  std::vector<double> last_published_commands_;
  std::vector<double> min_positions_;
  std::vector<double> max_positions_;
  std::vector<double> max_velocities_;
  double default_position_{0.0};
  double command_timeout_sec_{0.75};
  double state_following_gain_{1.0};
  double feedback_timeout_sec_{1.0};
  double command_publish_period_sec_{0.05};
  double gripper_open_position_{0.04};
  double gripper_closed_position_{0.0};
  double last_write_time_sec_{-1.0};
  double last_feedback_time_sec_{-1.0};
  double last_command_publish_time_sec_{-1.0};
  bool active_{false};
  bool transport_stale_{false};
  bool hardware_online_{false};
  bool hardware_faulted_{false};
  bool hardware_authoritative_{false};
  bool hardware_controllable_{false};
  bool state_stale_{true};
  bool last_gripper_open_{true};
  StateSourceMode state_source_mode_{StateSourceMode::ShadowFollowing};
  std::string command_topic_{"/arm/internal/hardware_cmd"};
  std::string state_topic_{"/arm/hardware/state"};
  std::string command_namespace_{"ros2_control_backbone"};
  std::shared_ptr<rclcpp::Node> bridge_node_;
  std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> bridge_executor_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr command_pub_;
  rclcpp::Subscription<arm_interfaces::msg::HardwareState>::SharedPtr state_sub_;
  std::thread bridge_thread_;
  std::atomic<bool> bridge_running_{false};
  std::atomic<unsigned long long> command_sequence_{0};
};

}  // namespace arm_hardware_interface
