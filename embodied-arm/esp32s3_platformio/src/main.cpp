#include <Adafruit_GFX.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_NeoPixel.h>
#include <Adafruit_SSD1306.h>
#include <Arduino.h>
#include <ArduinoJson.h>
#include <ESPmDNS.h>
#include <WebServer.h>
#include <WiFi.h>
#include <Wire.h>

#include "board_state.hpp"
#include "project_config.hpp"

using embodied_arm::esp32s3::BoardState;
using embodied_arm::esp32s3::VoiceEvent;

namespace {
using namespace embodied_arm::esp32s3;

class FirmwareApp {
 public:
  FirmwareApp()
      : server_(kHttpPort),
        strip_(kNeoPixelCount, kNeoPixelPin, NEO_GRB + NEO_KHZ800),
        display_(kOledWidth, kOledHeight, &Wire, -1) {}

  void begin() {
    Serial.begin(115200);
    delay(200);
    state_.hostname = EMBODIED_ARM_HOSTNAME;
    state_.stream_endpoint = String("http://") + state_.hostname + ".local" + kStreamPath;
    state_.camera_serial = kCameraSerial;
    state_.mode = kDefaultMode;

    initPeripherals();
    connectWifi();
    registerRoutes();
    server_.begin();
    pushVoiceEvent("boot", "system");
    Serial.println("[esp32s3] embodied arm board ready");
  }

  void loop() {
    server_.handleClient();
    const uint32_t now = millis();

    if (now - last_serial_poll_ms_ >= kSerialPhrasePollMs) {
      pollSerialPhrase();
      last_serial_poll_ms_ = now;
    }

    if (now - last_heartbeat_ms_ >= kHeartbeatPeriodMs) {
      sampleBoard();
      state_.heartbeat_counter += 1;
      last_heartbeat_ms_ = now;
      updateLed();
      publishConsoleHealth();
    }

    if (now - last_display_ms_ >= kDisplayPeriodMs) {
      updateDisplay();
      last_display_ms_ = now;
    }
  }

 private:
  void initPeripherals() {
    Wire.begin(kI2cSdaPin, kI2cSclPin);

    if (kEnableNeoPixel) {
      strip_.begin();
      strip_.clear();
      strip_.show();
      state_.led_available = true;
    }

    if (kEnableOled) {
      state_.display_available = display_.begin(SSD1306_SWITCHCAPVCC, kOledAddress);
      if (state_.display_available) {
        display_.clearDisplay();
        display_.setTextSize(1);
        display_.setTextColor(SSD1306_WHITE);
        display_.display();
      }
    }

    if (kEnableMpu6050) {
      state_.imu_available = mpu_.begin();
      if (state_.imu_available) {
        mpu_.setAccelerometerRange(MPU6050_RANGE_8_G);
        mpu_.setGyroRange(MPU6050_RANGE_500_DEG);
        mpu_.setFilterBandwidth(MPU6050_BAND_21_HZ);
      }
    }
  }

  void connectWifi() {
    WiFi.mode(WIFI_STA);
    WiFi.setHostname(EMBODIED_ARM_HOSTNAME);
    WiFi.begin(EMBODIED_ARM_WIFI_SSID, EMBODIED_ARM_WIFI_PASSWORD);

    const uint32_t deadline = millis() + 12000;
    while (WiFi.status() != WL_CONNECTED && millis() < deadline) {
      delay(250);
      if (state_.led_available) {
        strip_.setPixelColor(0, strip_.Color(16, 8, 0));
        strip_.show();
      }
    }

    state_.wifi_connected = WiFi.status() == WL_CONNECTED;
    if (state_.wifi_connected) {
      state_.ip_address = WiFi.localIP().toString();
      state_.stream_endpoint = String("http://") + state_.hostname + ".local" + kStreamPath;
      MDNS.begin(EMBODIED_ARM_HOSTNAME);
      MDNS.addService("http", "tcp", kHttpPort);
    } else {
      state_.ip_address = "0.0.0.0";
    }
  }

  void registerRoutes() {
    server_.on("/", HTTP_GET, [this]() { respondJson(buildStatusDocument(true)); });
    server_.on(kHealthPath, HTTP_GET, [this]() { respondJson(buildHealthDocument()); });
    server_.on(kStatusPath, HTTP_GET, [this]() { respondJson(buildStatusDocument(false)); });
    server_.on(kVoiceEventsPath, HTTP_GET, [this]() { respondJson(buildVoiceEventsDocument()); });
    server_.on(kVoiceCommandsPath, HTTP_GET, [this]() { respondJson(buildVoiceCommandsDocument()); });
    server_.on(kVoicePhrasePath, HTTP_POST, [this]() {
      const String phrase = extractPhrase();
      if (phrase.isEmpty()) {
        server_.send(400, "application/json", R"({"ok":false,"message":"missing phrase"})");
        return;
      }
      pushVoiceEvent(phrase, "http");
      JsonDocument doc;
      doc["ok"] = true;
      doc["phrase"] = phrase;
      doc["topic"] = "/arm/voice/events";
      respondJson(doc);
    });
    server_.on(kStreamPath, HTTP_GET, [this]() {
      JsonDocument doc;
      doc["available"] = state_.camera_available;
      doc["message"] = state_.camera_available
                            ? "camera-backed stream transport is provided by dedicated camera firmware or an external bridge"
                            : "stream endpoint reserved for camera firmware or external bridge";
      doc["streamPath"] = kStreamPath;
      doc["streamSemantic"] = state_.stream_semantic;
      doc["streamReserved"] = state_.stream_semantic == "reserved";
      doc["frameIngressLive"] = state_.frame_ingress_live;
      doc["frameIngressMode"] = state_.frame_ingress_live ? "live_camera_stream" : "reserved_endpoint";
      doc["deliveryModel"] = state_.camera_available ? "external_bridge_required" : "metadata_only";
      doc["supportsMjpeg"] = false;
      doc["streamEndpoint"] = state_.stream_endpoint;
      doc["cameraSerial"] = state_.camera_serial;
      respondJson(doc, state_.camera_available ? 200 : 501);
    });
    server_.onNotFound([this]() {
      JsonDocument doc;
      doc["ok"] = false;
      doc["message"] = "route not found";
      doc["path"] = server_.uri();
      respondJson(doc, 404);
    });
  }

  void sampleBoard() {
    state_.uptime_ms = millis();
    state_.wifi_connected = WiFi.status() == WL_CONNECTED;
    state_.wifi_rssi = state_.wifi_connected ? WiFi.RSSI() : 0;
    state_.ip_address = state_.wifi_connected ? WiFi.localIP().toString() : "0.0.0.0";

    if (state_.imu_available) {
      sensors_event_t accel;
      sensors_event_t gyro;
      sensors_event_t temp;
      mpu_.getEvent(&accel, &gyro, &temp);
      state_.accel_x = accel.acceleration.x;
      state_.accel_y = accel.acceleration.y;
      state_.accel_z = accel.acceleration.z;
      state_.gyro_x = gyro.gyro.x;
      state_.gyro_y = gyro.gyro.y;
      state_.gyro_z = gyro.gyro.z;
    }
  }

  void updateLed() {
    if (!state_.led_available) {
      return;
    }
    uint32_t color = strip_.Color(0, 0, 12);
    if (state_.wifi_connected) {
      color = strip_.Color(0, 18, 0);
    }
    if (!state_.display_available || !state_.imu_available) {
      color = strip_.Color(18, 10, 0);
    }
    strip_.setPixelColor(0, color);
    strip_.show();
  }

  void updateDisplay() {
    if (!state_.display_available) {
      return;
    }
    display_.clearDisplay();
    display_.setCursor(0, 0);
    display_.printf("Embodied Arm\n");
    display_.printf("WiFi: %s\n", state_.wifi_connected ? "up" : "down");
    display_.printf("IP: %s\n", state_.ip_address.c_str());
    display_.printf("HB: %lu\n", static_cast<unsigned long>(state_.heartbeat_counter));
    display_.printf("stream:%s\n", state_.stream_semantic.c_str());
    display_.display();
  }

  void publishConsoleHealth() {
    JsonDocument doc = buildHealthDocument();
    serializeJson(doc, Serial);
    Serial.println();
  }

  void pollSerialPhrase() {
    while (Serial.available() > 0) {
      const char c = static_cast<char>(Serial.read());
      if (c == '\n' || c == '\r') {
        serial_buffer_.trim();
        if (!serial_buffer_.isEmpty()) {
          pushVoiceEvent(serial_buffer_, "serial");
          serial_buffer_.clear();
        }
      } else {
        serial_buffer_ += c;
      }
    }
  }

  void pushVoiceEvent(const String& phrase, const String& source) {
    VoiceEvent event;
    event.phrase = phrase;
    event.source = source;
    event.stamp_ms = millis();
    state_.voice_history.push_back(event);
    if (state_.voice_history.size() > kVoiceHistoryDepth) {
      state_.voice_history.erase(state_.voice_history.begin());
    }
  }

  String extractPhrase() {
    if (server_.hasArg("phrase")) {
      return server_.arg("phrase");
    }
    if (server_.hasArg("plain")) {
      JsonDocument doc;
      const DeserializationError err = deserializeJson(doc, server_.arg("plain"));
      if (!err && doc["phrase"].is<const char*>()) {
        return String(doc["phrase"].as<const char*>());
      }
      return server_.arg("plain");
    }
    return String();
  }

  JsonDocument buildHealthDocument() const {
    JsonDocument doc;
    doc["online"] = state_.online;
    doc["mode"] = state_.mode;
    doc["hostname"] = state_.hostname;
    doc["ip"] = state_.ip_address;
    doc["stream_endpoint"] = state_.stream_endpoint;
    doc["stream_semantic"] = state_.stream_semantic;
    doc["stream_reserved"] = state_.stream_semantic == "reserved";
    doc["frame_ingress_live"] = state_.frame_ingress_live;
    doc["camera_serial"] = state_.camera_serial;
    doc["heartbeat_counter"] = state_.heartbeat_counter;
    doc["uptime_ms"] = state_.uptime_ms;
    doc["wifi_connected"] = state_.wifi_connected;
    doc["wifi_rssi"] = state_.wifi_rssi;
    doc["imu_available"] = state_.imu_available;
    doc["display_available"] = state_.display_available;
    doc["led_available"] = state_.led_available;
    doc["camera_available"] = state_.camera_available;
    JsonObject motion = doc["imu"].to<JsonObject>();
    motion["accel_x"] = state_.accel_x;
    motion["accel_y"] = state_.accel_y;
    motion["accel_z"] = state_.accel_z;
    motion["gyro_x"] = state_.gyro_x;
    motion["gyro_y"] = state_.gyro_y;
    motion["gyro_z"] = state_.gyro_z;
    return doc;
  }

  JsonDocument buildStatusDocument(bool include_voice) const {
    JsonDocument doc = buildHealthDocument();
    doc["topic"] = "/arm/hardware/esp32_link";
    doc["transport"] = "wifi";
    doc["voice_topic"] = "/arm/voice/events";
    doc["status_notifier_state"] = state_.wifi_connected ? "online" : "degraded";
    if (include_voice) {
      JsonArray history = doc["voice_history"].to<JsonArray>();
      for (const auto& item : state_.voice_history) {
        JsonObject entry = history.add<JsonObject>();
        entry["phrase"] = item.phrase;
        entry["source"] = item.source;
        entry["stamp_ms"] = item.stamp_ms;
      }
    }
    return doc;
  }

  JsonDocument buildVoiceEventsDocument() const {
    JsonDocument doc;
    doc["topic"] = "/arm/voice/events";
    JsonArray events = doc["events"].to<JsonArray>();
    for (const auto& item : state_.voice_history) {
      JsonObject entry = events.add<JsonObject>();
      entry["phrase"] = item.phrase;
      entry["source"] = item.source;
      entry["stamp_ms"] = item.stamp_ms;
    }
    return doc;
  }

  JsonDocument buildVoiceCommandsDocument() const {
    JsonDocument doc;
    JsonArray commands = doc["commands"].to<JsonArray>();
    commands.add("start");
    commands.add("stop");
    commands.add("home");
    commands.add("open gripper");
    commands.add("close gripper");
    commands.add("emergency stop");
    doc["topic"] = "/arm/voice/events";
    return doc;
  }

  void respondJson(const JsonDocument& doc, int status = 200) {
    String payload;
    serializeJson(doc, payload);
    server_.send(status, "application/json", payload);
  }

  WebServer server_;
  Adafruit_NeoPixel strip_;
  Adafruit_SSD1306 display_;
  Adafruit_MPU6050 mpu_;
  BoardState state_{};
  uint32_t last_heartbeat_ms_{0};
  uint32_t last_display_ms_{0};
  uint32_t last_serial_poll_ms_{0};
  String serial_buffer_;
};

FirmwareApp app;
}  // namespace

void setup() { app.begin(); }
void loop() { app.loop(); }
