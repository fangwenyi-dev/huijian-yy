# huijian AI

Home Assistant 自定义集成，支持 ESPHome 设备的语音助手、语音转文字（STT）、文字转语音（TTS）以及 LLM 智能家居控制功能。

## 功能特性

- 语音助手卫星 - 将 ESPHome 设备作为语音助手卫星使用
- 语音识别（STT）- 支持语音转文字功能
- 语音合成（TTS）- 支持文字转语音功能
- LLM 集成 - 支持与大语言模型集成实现智能对话控制
- MCP 传输 - 支持 Model Control Protocol 传输协议
- 蓝牙支持 - 集成蓝牙功能
- 设备发现 - 支持 mDNS、MQTT、DHCP、Zeroconf 等多种发现方式
- 二维码配网 - 通过二维码快速配置设备

## 支持的设备类型

- 灯光 (light)
- 空调 (climate)
- 窗帘/窗户 (cover)
- 开关 (switch)
- 媒体播放器 (media_player)
- 锁 (lock)
- 加湿器/除湿器 (humidifier)
- 风扇 (fan)
- 传感器 (sensor)

## 安装

1. 通过 HACS 添加自定义仓库 `https://github.com/fangwenyi-dev/huijian-yy`
2. 搜索并安装 `huijian AI`
3. 重启 Home Assistant

## 配置

在 Home Assistant 的 **设置** → **设备与服务** → **添加集成** 中搜索 `huijian AI` 进行配置。

## 版本要求

- Home Assistant 最新版本
- Python 3.13+

## 支持的 ESPHome 设备

- ESP32 / ESP32-S3 开发板
- ESP32 蓝牙代理
- 支持语音功能的自定义设备