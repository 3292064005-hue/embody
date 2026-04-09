# System Release Manifest

根级 release manifest 由 `scripts/package_split_release.py` 生成，输出到 `artifacts/split_release_manifest.json`。

manifest 当前至少锁定：

- `systemVersion`
- `upperComputerVersion`
- `esp32FirmwareVersion`
- `stm32FirmwareVersion`
- `protocolVersion`
- `compatibility`
- `files`

该文件是 split 三段式交付的最小系统级版本基线，不再只依赖 `upper_computer/` 子目录的发布视角。

## 本地离线验证与 CI 的边界

- 本地 `make verify` 会先执行 firmware source contract 校验，确保 `platformio.ini`、关键源文件、ESP32 路由语义、STM32 命令枚举与串口协议文档一致。
- 若本机已经预装 `~/.platformio/platforms/espressif32` 与 `~/.platformio/platforms/ststm32`，同一条验证链会继续执行真实 `pio run`。
- 若本机没有这些 platform 包，则本地验证不会伪装成“已编译通过”，而是显式把真实固件编译留给 CI 或联网工作站。
