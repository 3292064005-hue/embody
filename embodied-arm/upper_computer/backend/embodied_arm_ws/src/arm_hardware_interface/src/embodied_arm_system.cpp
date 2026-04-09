#include "arm_hardware_interface/embodied_arm_system.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <string>
#include <unordered_map>

#include "pluginlib/class_list_macros.hpp"

namespace arm_hardware_interface {

namespace {
constexpr double kDefaultMinPosition = -3.14159265358979323846;
constexpr double kDefaultMaxPosition = 3.14159265358979323846;
constexpr double kDefaultMaxVelocity = 1.5;
constexpr double kCommandEpsilon = 1e-6;
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

hardware_interface::CallbackReturn EmbodiedArmSystemInterface::on_init(const hardware_interface::HardwareInfo & info) {
  if (hardware_interface::SystemInterface::on_init(info) != hardware_interface::CallbackReturn::SUCCESS) {
    return hardware_interface::CallbackReturn::ERROR;
  }

  const std::size_t joint_count = info_.joints.size();
  hw_positions_.assign(joint_count, 0.0);
  hw_velocities_.assign(joint_count, 0.0);
  hw_commands_.assign(joint_count, 0.0);
  min_positions_.assign(joint_count, kDefaultMinPosition);
  max_positions_.assign(joint_count, kDefaultMaxPosition);
  max_velocities_.assign(joint_count, kDefaultMaxVelocity);

  default_position_ = parse_parameter_or_default(info_.hardware_parameters, "default_position", 0.0);
  command_timeout_sec_ = std::max(0.05, parse_parameter_or_default(info_.hardware_parameters, "command_timeout_sec", 0.75));
  state_following_gain_ = std::max(0.1, parse_parameter_or_default(info_.hardware_parameters, "state_following_gain", 1.0));
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
  last_write_time_sec_ = -1.0;
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

hardware_interface::CallbackReturn EmbodiedArmSystemInterface::on_activate(const rclcpp_lifecycle::State &) {
  for (std::size_t i = 0; i < hw_positions_.size(); ++i) {
    hw_positions_[i] = std::clamp(default_position_, min_positions_[i], max_positions_[i]);
    hw_commands_[i] = hw_positions_[i];
    hw_velocities_[i] = 0.0;
  }
  active_ = true;
  transport_stale_ = false;
  last_write_time_sec_ = -1.0;
  return hardware_interface::CallbackReturn::SUCCESS;
}

hardware_interface::CallbackReturn EmbodiedArmSystemInterface::on_deactivate(const rclcpp_lifecycle::State &) {
  for (double & velocity : hw_velocities_) {
    velocity = 0.0;
  }
  active_ = false;
  transport_stale_ = false;
  return hardware_interface::CallbackReturn::SUCCESS;
}

double EmbodiedArmSystemInterface::clamp_command(double value, std::size_t index) const {
  if (!std::isfinite(value)) {
    return hw_positions_[index];
  }
  return std::clamp(value, min_positions_[index], max_positions_[index]);
}

hardware_interface::return_type EmbodiedArmSystemInterface::read(const rclcpp::Time & time, const rclcpp::Duration & period) {
  if (!active_) {
    return hardware_interface::return_type::OK;
  }

  const double now_sec = time.seconds();
  const double dt = std::max(0.0, period.seconds());
  transport_stale_ = last_write_time_sec_ >= 0.0 && (now_sec - last_write_time_sec_) > command_timeout_sec_;
  if (transport_stale_) {
    std::fill(hw_velocities_.begin(), hw_velocities_.end(), 0.0);
    return hardware_interface::return_type::ERROR;
  }

  for (std::size_t i = 0; i < hw_positions_.size(); ++i) {
    const double target = clamp_command(hw_commands_[i], i);
    const double delta = target - hw_positions_[i];
    const double max_step = max_velocities_[i] * std::max(dt, kCommandEpsilon) * state_following_gain_;
    double applied_step = 0.0;
    if (std::fabs(delta) <= kCommandEpsilon) {
      hw_positions_[i] = target;
      hw_velocities_[i] = 0.0;
      continue;
    }
    if (max_step <= kCommandEpsilon) {
      hw_velocities_[i] = 0.0;
      continue;
    }
    applied_step = std::clamp(delta, -max_step, max_step);
    hw_positions_[i] = clamp_command(hw_positions_[i] + applied_step, i);
    hw_velocities_[i] = dt > kCommandEpsilon ? applied_step / dt : 0.0;
  }
  return hardware_interface::return_type::OK;
}

hardware_interface::return_type EmbodiedArmSystemInterface::write(const rclcpp::Time & time, const rclcpp::Duration &) {
  if (!active_) {
    return hardware_interface::return_type::OK;
  }
  for (std::size_t i = 0; i < hw_commands_.size(); ++i) {
    hw_commands_[i] = clamp_command(hw_commands_[i], i);
  }
  last_write_time_sec_ = time.seconds();
  transport_stale_ = false;
  return hardware_interface::return_type::OK;
}

}  // namespace arm_hardware_interface

PLUGINLIB_EXPORT_CLASS(arm_hardware_interface::EmbodiedArmSystemInterface, hardware_interface::SystemInterface)
