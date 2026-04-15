#include "arm_hardware_interface/embodied_arm_system.hpp"

#include <algorithm>
#include <cmath>
#include <chrono>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <utility>

#include "pluginlib/class_list_macros.hpp"

namespace arm_hardware_interface {

namespace {
constexpr double kDefaultMinPosition = -3.14159265358979323846;
constexpr double kDefaultMaxPosition = 3.14159265358979323846;
constexpr double kDefaultMaxVelocity = 1.5;
constexpr double kCommandEpsilon = 1e-6;
constexpr double kGripperThreshold = 0.02;
}  // namespace

double EmbodiedArmSystemInterface::parse_parameter_or_default(
    const std::unordered_map<std::string, std::string> & parameters,
    const std::string & key,
    double fallback) {
  const auto it = parameters.find(key);
  if (it == parameters.end()) {
    return fallback;
  }
  try {
    return std::stod(it->second);
  } catch (...) {
    return fallback;
  }
}

bool EmbodiedArmSystemInterface::parse_bool_parameter_or_default(
    const std::unordered_map<std::string, std::string> & parameters,
    const std::string & key,
    bool fallback) {
  const auto it = parameters.find(key);
  if (it == parameters.end()) {
    return fallback;
  }
  const auto value = it->second;
  if (value == "true" || value == "1" || value == "yes" || value == "on") {
    return true;
  }
  if (value == "false" || value == "0" || value == "no" || value == "off") {
    return false;
  }
  return fallback;
}

std::string EmbodiedArmSystemInterface::parse_string_parameter_or_default(
    const std::unordered_map<std::string, std::string> & parameters,
    const std::string & key,
    const std::string & fallback) {
  const auto it = parameters.find(key);
  if (it == parameters.end() || it->second.empty()) {
    return fallback;
  }
  return it->second;
}

EmbodiedArmSystemInterface::StateSourceMode EmbodiedArmSystemInterface::parse_state_source_mode(
    const std::unordered_map<std::string, std::string> & parameters) {
  const auto mode = parse_string_parameter_or_default(parameters, "state_source_mode", "shadow_following");
  if (mode == "external_feedback") {
    return StateSourceMode::ExternalFeedback;
  }
  return StateSourceMode::ShadowFollowing;
}

bool EmbodiedArmSystemInterface::extract_named_bool_from_raw_status(const std::string & raw_status, const std::string & key, bool fallback) {
  const auto true_token = std::string("\"") + key + "\":true";
  const auto true_token_spaced = std::string("\"") + key + "\": true";
  const auto false_token = std::string("\"") + key + "\":false";
  const auto false_token_spaced = std::string("\"") + key + "\": false";
  if (raw_status.find(true_token) != std::string::npos || raw_status.find(true_token_spaced) != std::string::npos) {
    return true;
  }
  if (raw_status.find(false_token) != std::string::npos || raw_status.find(false_token_spaced) != std::string::npos) {
    return false;
  }
  return fallback;
}

bool EmbodiedArmSystemInterface::extract_gripper_open_from_raw_status(const std::string & raw_status, bool fallback) {
  return extract_named_bool_from_raw_status(raw_status, "gripper_open", fallback);
}

hardware_interface::CallbackReturn EmbodiedArmSystemInterface::on_init(const hardware_interface::HardwareInfo & info) {
  if (hardware_interface::SystemInterface::on_init(info) != hardware_interface::CallbackReturn::SUCCESS) {
    return hardware_interface::CallbackReturn::ERROR;
  }

  const std::size_t joint_count = info_.joints.size();
  hw_positions_.assign(joint_count, 0.0);
  hw_velocities_.assign(joint_count, 0.0);
  hw_commands_.assign(joint_count, 0.0);
  last_published_commands_.assign(joint_count, std::numeric_limits<double>::quiet_NaN());
  min_positions_.assign(joint_count, kDefaultMinPosition);
  max_positions_.assign(joint_count, kDefaultMaxPosition);
  max_velocities_.assign(joint_count, kDefaultMaxVelocity);

  default_position_ = parse_parameter_or_default(info_.hardware_parameters, "default_position", 0.0);
  command_timeout_sec_ = std::max(0.05, parse_parameter_or_default(info_.hardware_parameters, "command_timeout_sec", 0.75));
  state_following_gain_ = std::max(0.1, parse_parameter_or_default(info_.hardware_parameters, "state_following_gain", 1.0));
  feedback_timeout_sec_ = std::max(0.1, parse_parameter_or_default(info_.hardware_parameters, "feedback_timeout_sec", command_timeout_sec_));
  command_publish_period_sec_ = std::max(0.01, parse_parameter_or_default(info_.hardware_parameters, "command_publish_period_sec", 0.05));
  gripper_open_position_ = parse_parameter_or_default(info_.hardware_parameters, "gripper_open_position", 0.04);
  gripper_closed_position_ = parse_parameter_or_default(info_.hardware_parameters, "gripper_closed_position", 0.0);
  command_topic_ = parse_string_parameter_or_default(info_.hardware_parameters, "command_topic", "/arm/internal/hardware_cmd");
  state_topic_ = parse_string_parameter_or_default(info_.hardware_parameters, "state_topic", "/arm/hardware/state");
  command_namespace_ = parse_string_parameter_or_default(info_.hardware_parameters, "command_namespace", "ros2_control_backbone");
  state_source_mode_ = parse_state_source_mode(info_.hardware_parameters);
  const double default_max_velocity = std::max(0.01, parse_parameter_or_default(info_.hardware_parameters, "default_max_velocity", kDefaultMaxVelocity));

  for (std::size_t i = 0; i < joint_count; ++i) {
    const auto & joint = info_.joints[i];
    if (joint.command_interfaces.size() != 1 || joint.command_interfaces[0].name != hardware_interface::HW_IF_POSITION) {
      return hardware_interface::CallbackReturn::ERROR;
    }
    if (joint.state_interfaces.size() < 2) {
      return hardware_interface::CallbackReturn::ERROR;
    }
    min_positions_[i] = parse_parameter_or_default(joint.parameters, "min_position", kDefaultMinPosition);
    max_positions_[i] = parse_parameter_or_default(joint.parameters, "max_position", kDefaultMaxPosition);
    if (min_positions_[i] > max_positions_[i]) {
      std::swap(min_positions_[i], max_positions_[i]);
    }
    max_velocities_[i] = std::max(0.01, parse_parameter_or_default(joint.parameters, "max_velocity", default_max_velocity));
    hw_positions_[i] = std::clamp(default_position_, min_positions_[i], max_positions_[i]);
    hw_commands_[i] = hw_positions_[i];
  }

  active_ = false;
  transport_stale_ = false;
  hardware_online_ = false;
  hardware_faulted_ = false;
  last_feedback_time_sec_ = -1.0;
  last_write_time_sec_ = -1.0;
  last_command_publish_time_sec_ = -1.0;
  bridge_running_.store(false);
  command_sequence_.store(0);
  return hardware_interface::CallbackReturn::SUCCESS;
}

std::vector<hardware_interface::StateInterface> EmbodiedArmSystemInterface::export_state_interfaces() {
  std::vector<hardware_interface::StateInterface> interfaces;
  interfaces.reserve(info_.joints.size() * 2);
  for (std::size_t i = 0; i < info_.joints.size(); ++i) {
    interfaces.emplace_back(info_.joints[i].name, hardware_interface::HW_IF_POSITION, &hw_positions_[i]);
    interfaces.emplace_back(info_.joints[i].name, hardware_interface::HW_IF_VELOCITY, &hw_velocities_[i]);
  }
  return interfaces;
}

std::vector<hardware_interface::CommandInterface> EmbodiedArmSystemInterface::export_command_interfaces() {
  std::vector<hardware_interface::CommandInterface> interfaces;
  interfaces.reserve(info_.joints.size());
  for (std::size_t i = 0; i < info_.joints.size(); ++i) {
    interfaces.emplace_back(info_.joints[i].name, hardware_interface::HW_IF_POSITION, &hw_commands_[i]);
  }
  return interfaces;
}

void EmbodiedArmSystemInterface::ensure_ros_bridge_started() {
  if (bridge_running_.load()) {
    return;
  }
  if (!rclcpp::ok()) {
    throw std::runtime_error("rclcpp runtime unavailable for external_feedback hardware interface");
  }
  rclcpp::NodeOptions options;
  options.start_parameter_services(false);
  options.start_parameter_event_publisher(false);
  bridge_node_ = std::make_shared<rclcpp::Node>("embodied_arm_system_interface_bridge", options);
  command_pub_ = bridge_node_->create_publisher<std_msgs::msg::String>(command_topic_, 20);
  state_sub_ = bridge_node_->create_subscription<arm_interfaces::msg::HardwareState>(
      state_topic_, 20, [this](const arm_interfaces::msg::HardwareState::SharedPtr msg) { this->handle_hardware_state(msg); });
  bridge_executor_ = std::make_shared<rclcpp::executors::SingleThreadedExecutor>();
  bridge_executor_->add_node(bridge_node_);
  bridge_running_.store(true);
  bridge_thread_ = std::thread([this]() {
    while (bridge_running_.load()) {
      bridge_executor_->spin_some();
      std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
  });
}

void EmbodiedArmSystemInterface::shutdown_ros_bridge() {
  bridge_running_.store(false);
  if (bridge_thread_.joinable()) {
    bridge_thread_.join();
  }
  if (bridge_executor_ && bridge_node_) {
    bridge_executor_->remove_node(bridge_node_);
  }
  state_sub_.reset();
  command_pub_.reset();
  bridge_executor_.reset();
  bridge_node_.reset();
}

hardware_interface::CallbackReturn EmbodiedArmSystemInterface::on_activate(const rclcpp_lifecycle::State &) {
  {
    std::lock_guard<std::mutex> lock(state_mutex_);
    for (std::size_t i = 0; i < hw_positions_.size(); ++i) {
      hw_positions_[i] = std::clamp(default_position_, min_positions_[i], max_positions_[i]);
      hw_commands_[i] = hw_positions_[i];
      hw_velocities_[i] = 0.0;
      last_published_commands_[i] = std::numeric_limits<double>::quiet_NaN();
    }
    active_ = true;
    transport_stale_ = false;
    hardware_online_ = state_source_mode_ == StateSourceMode::ShadowFollowing;
    hardware_faulted_ = false;
    hardware_authoritative_ = state_source_mode_ == StateSourceMode::ShadowFollowing;
    hardware_controllable_ = state_source_mode_ == StateSourceMode::ShadowFollowing;
    state_stale_ = state_source_mode_ != StateSourceMode::ShadowFollowing;
    last_feedback_time_sec_ = -1.0;
    last_write_time_sec_ = -1.0;
    last_command_publish_time_sec_ = -1.0;
  }
  try {
    if (state_source_mode_ == StateSourceMode::ExternalFeedback) {
      ensure_ros_bridge_started();
    }
  } catch (...) {
    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      active_ = false;
    }
    shutdown_ros_bridge();
    return hardware_interface::CallbackReturn::ERROR;
  }
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn EmbodiedArmSystemInterface::on_deactivate(const rclcpp_lifecycle::State &) {
  {
    std::lock_guard<std::mutex> lock(state_mutex_);
    for (double & velocity : hw_velocities_) {
      velocity = 0.0;
    }
    active_ = false;
    transport_stale_ = false;
    hardware_online_ = false;
    hardware_faulted_ = false;
    hardware_authoritative_ = false;
    hardware_controllable_ = false;
    state_stale_ = true;
  }
  shutdown_ros_bridge();
  return hardware_interface::CallbackReturn::SUCCESS;
}

double EmbodiedArmSystemInterface::clamp_command(double value, std::size_t index) const {
  if (!std::isfinite(value)) {
    return hw_positions_[index];
  }
  return std::clamp(value, min_positions_[index], max_positions_[index]);
}

void EmbodiedArmSystemInterface::handle_hardware_state(const arm_interfaces::msg::HardwareState::SharedPtr msg) {
  if (!msg) {
    return;
  }
  std::lock_guard<std::mutex> lock(state_mutex_);
  const auto positions = msg->joint_position;
  const auto velocities = msg->joint_velocity;
  const std::size_t arm_count = std::min<std::size_t>(positions.size(), arm_joint_names().size());
  for (std::size_t i = 0; i < arm_count; ++i) {
    hw_positions_[i] = clamp_command(static_cast<double>(positions[i]), i);
  }
  for (std::size_t i = 0; i < arm_count; ++i) {
    hw_velocities_[i] = i < velocities.size() ? static_cast<double>(velocities[i]) : 0.0;
  }
  if (hw_positions_.size() > arm_count) {
    const bool gripper_open = extract_gripper_open_from_raw_status(msg->raw_status, last_gripper_open_);
    last_gripper_open_ = gripper_open;
    const std::size_t gripper_index = hw_positions_.size() - 1;
    hw_positions_[gripper_index] = gripper_open ? gripper_open_position_ : gripper_closed_position_;
    hw_velocities_[gripper_index] = 0.0;
  }
  hardware_online_ = bool(msg->stm32_online);
  hardware_faulted_ = static_cast<unsigned int>(msg->hardware_fault_code) != 0U || bool(msg->estop_pressed) || bool(msg->limit_triggered);
  hardware_authoritative_ = extract_named_bool_from_raw_status(msg->raw_status, "hardwareAuthoritative", extract_named_bool_from_raw_status(msg->raw_status, "authoritative", false));
  hardware_controllable_ = extract_named_bool_from_raw_status(msg->raw_status, "hardwareControllable", extract_named_bool_from_raw_status(msg->raw_status, "controllable", false));
  state_stale_ = extract_named_bool_from_raw_status(msg->raw_status, "state_stale", true);
  last_feedback_time_sec_ = bridge_node_ ? bridge_node_->get_clock()->now().seconds() : last_feedback_time_sec_;
}

std::vector<std::string> EmbodiedArmSystemInterface::arm_joint_names() const {
  std::vector<std::string> names;
  for (const auto & joint : info_.joints) {
    if (joint.name != "gripper_joint") {
      names.push_back(joint.name);
    }
  }
  return names;
}

bool EmbodiedArmSystemInterface::command_changed() const {
  for (std::size_t i = 0; i < hw_commands_.size(); ++i) {
    if (!std::isfinite(last_published_commands_[i])) {
      return true;
    }
    if (std::fabs(hw_commands_[i] - last_published_commands_[i]) > kCommandEpsilon) {
      return true;
    }
  }
  return false;
}

bool EmbodiedArmSystemInterface::command_publish_due(double now_sec) const {
  if (last_command_publish_time_sec_ < 0.0) {
    return true;
  }
  if (command_changed()) {
    return true;
  }
  return (now_sec - last_command_publish_time_sec_) >= command_publish_period_sec_;
}

std::string EmbodiedArmSystemInterface::build_set_joints_command_json() const {
  std::ostringstream stream;
  const auto arm_names = arm_joint_names();
  const std::size_t arm_count = arm_names.size();
  const std::size_t gripper_index = hw_commands_.empty() ? 0U : hw_commands_.size() - 1U;
  const bool include_gripper = hw_commands_.size() > arm_count;
  const bool gripper_open = include_gripper ? hw_commands_[gripper_index] >= kGripperThreshold : last_gripper_open_;
  const auto sequence = command_sequence_.load() + 1ULL;
  stream << "{";
  stream << "\"command_id\":\"" << command_namespace_ << ":" << sequence << "\",";
  stream << "\"plan_id\":\"" << command_namespace_ << "\",";
  stream << "\"task_id\":\"" << command_namespace_ << "\",";
  stream << "\"stage\":\"follow_joint_trajectory\",";
  stream << "\"kind\":\"SET_JOINTS\",";
  stream << "\"timeout_sec\":" << command_timeout_sec_ << ",";
  stream << "\"joint_names\":[";
  for (std::size_t i = 0; i < arm_count; ++i) {
    if (i > 0U) {
      stream << ',';
    }
    stream << "\"" << arm_names[i] << "\"";
  }
  stream << "],";
  stream << "\"joint_positions\":[";
  for (std::size_t i = 0; i < arm_count; ++i) {
    if (i > 0U) {
      stream << ',';
    }
    stream << hw_commands_[i];
  }
  stream << "],";
  stream << "\"gripper_open\":" << (gripper_open ? "true" : "false") << ",";
  stream << "\"gripper_position\":" << (include_gripper ? hw_commands_[gripper_index] : (gripper_open ? gripper_open_position_ : gripper_closed_position_)) << ",";
  stream << "\"source\":\"ros2_control\",";
  stream << "\"producer\":\"" << command_namespace_ << "\",";
  stream << "\"command_plane\":\"joint_stream\",";
  stream << "\"transport_backbone\":\"dispatcher\"";
  stream << "}";
  return stream.str();
}

hardware_interface::return_type EmbodiedArmSystemInterface::read(const rclcpp::Time & time, const rclcpp::Duration & period) {
  if (!active_) {
    return hardware_interface::return_type::OK;
  }

  const double now_sec = time.seconds();
  const double dt = std::max(0.0, period.seconds());
  if (state_source_mode_ == StateSourceMode::ShadowFollowing) {
    transport_stale_ = last_write_time_sec_ >= 0.0 && (now_sec - last_write_time_sec_) > command_timeout_sec_;
    if (transport_stale_) {
      std::fill(hw_velocities_.begin(), hw_velocities_.end(), 0.0);
      return hardware_interface::return_type::ERROR;
    }
    for (std::size_t i = 0; i < hw_positions_.size(); ++i) {
      const double target = clamp_command(hw_commands_[i], i);
      const double delta = target - hw_positions_[i];
      const double max_step = max_velocities_[i] * std::max(dt, kCommandEpsilon) * state_following_gain_;
      if (std::fabs(delta) <= kCommandEpsilon) {
        hw_positions_[i] = target;
        hw_velocities_[i] = 0.0;
        continue;
      }
      if (max_step <= kCommandEpsilon) {
        hw_velocities_[i] = 0.0;
        continue;
      }
      const double applied_step = std::clamp(delta, -max_step, max_step);
      hw_positions_[i] = clamp_command(hw_positions_[i] + applied_step, i);
      hw_velocities_[i] = dt > kCommandEpsilon ? applied_step / dt : 0.0;
    }
    return hardware_interface::return_type::OK;
  }

  std::lock_guard<std::mutex> lock(state_mutex_);
  transport_stale_ = last_feedback_time_sec_ < 0.0 || (now_sec - last_feedback_time_sec_) > feedback_timeout_sec_ || !hardware_online_ || hardware_faulted_ || !hardware_authoritative_ || !hardware_controllable_ || state_stale_;
  if (transport_stale_) {
    std::fill(hw_velocities_.begin(), hw_velocities_.end(), 0.0);
    return hardware_interface::return_type::ERROR;
  }
  return hardware_interface::return_type::OK;
}

hardware_interface::return_type EmbodiedArmSystemInterface::write(const rclcpp::Time & time, const rclcpp::Duration &) {
  if (!active_) {
    return hardware_interface::return_type::OK;
  }
  std::lock_guard<std::mutex> lock(state_mutex_);
  for (std::size_t i = 0; i < hw_commands_.size(); ++i) {
    hw_commands_[i] = clamp_command(hw_commands_[i], i);
  }
  last_write_time_sec_ = time.seconds();
  if (state_source_mode_ == StateSourceMode::ShadowFollowing) {
    transport_stale_ = false;
    return hardware_interface::return_type::OK;
  }
  if (!command_pub_ || !bridge_running_.load()) {
    transport_stale_ = true;
    return hardware_interface::return_type::ERROR;
  }
  if (!command_publish_due(time.seconds())) {
    transport_stale_ = false;
    return hardware_interface::return_type::OK;
  }
  std_msgs::msg::String payload;
  payload.data = build_set_joints_command_json();
  command_pub_->publish(payload);
  last_published_commands_ = hw_commands_;
  last_command_publish_time_sec_ = time.seconds();
  command_sequence_.fetch_add(1ULL);
  transport_stale_ = false;
  return hardware_interface::return_type::OK;
}

}  // namespace arm_hardware_interface

PLUGINLIB_EXPORT_CLASS(arm_hardware_interface::EmbodiedArmSystemInterface, hardware_interface::SystemInterface)
