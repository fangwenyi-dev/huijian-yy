# huijian AI - Home Assistant 自定义集成

一个用于 Home Assistant 的自定义集成，支持 ESPHome 设备的语音助手、语音转文字（STT）、文字转语音（TTS）以及 LLM 智能家居控制功能。

## 功能特性

- **语音助手卫星**：将 ESPHome 设备作为语音助手卫星使用
- **语音识别（STT）**：支持语音转文字功能
- **语音合成（TTS）**：支持文字转语音功能
- **LLM 集成**：支持与大语言模型集成实现智能对话控制
- **MCP 传输**：支持 Model Control Protocol 传输协议
- **蓝牙支持**：集成蓝牙功能
- **设备发现**：支持 mDNS、MQTT、DHCP、Zeroconf 等多种发现方式
- **二维码配网**：通过二维码快速配置设备
- **加密通信**：支持 Noise Protocol 加密确保通信安全

## 支持的意图

集成支持以下语音意图，可通过 LLM 语音助手触发：

### 设备控制

| 意图名称 | 说明 | 示例语音 |
|---------|------|---------|
| `TurnDeviceOn` | 打开设备 | "打开卧室灯"、"打开窗户"、"按场景按钮" |
| `TurnDeviceOff` | 关闭设备 | "关闭卧室灯"、"关闭窗户" |

### 设备调节

| 意图名称 | 属性 | 支持平台 | 示例语音 |
|---------|------|---------|---------|
| `AdjustDeviceAttribute` | `brightness` | 灯光 | "灯调亮一点"、"亮度调到50%" |
| `AdjustDeviceAttribute` | `color` | 灯光 | "灯调成蓝色"、"颜色改成#FF0000" |
| `AdjustDeviceAttribute` | `temperature` | 灯光、空调 | "色温调高一点"、"温度调到26度" |
| `AdjustDeviceAttribute` | `fan_speed` | 风扇、空调 | "风速调大一档"、"空风扇调到中速" |
| `AdjustDeviceAttribute` | `humidity` | 加湿器 | "湿度调到60%" |
| `AdjustDeviceAttribute` | `position` | 窗帘 | "窗帘开50%"、"窗户关一半" |

### 模式设置

| 意图名称 | 说明 | 支持平台 | 示例语音 |
|---------|------|---------|---------|
| `SetDeviceMode` | 设置设备模式 | 空调、加湿器 | "空调调到制冷模式"、"加湿器调到静音模式" |

### 窗户控制

| 意图名称 | 说明 | 示例语音 |
|---------|------|---------|
| `ControlWindow` | 控制窗户 | "打开平推窗"、"关闭窗户"、"窗户暂停" |

### 实时上下文

| 意图名称 | 说明 | 用途 |
|---------|------|------|
| `huijianGetLiveContext` | 获取实时设备状态 | 用于回答"灯开着吗？"、"现在温度多少？"等问题 |

### 语音场景

| 意图名称 | 说明 | 示例语音 |
|---------|------|---------|
| `HassCreateVoiceScene` | 创建语音场景 | "当我说'晚安模式'的时候，帮我关灯并锁门" |
| `HassTriggerVoiceScene` | 触发语音场景 | "晚安模式" |
| `HassDeleteVoiceScene` | 删除语音场景 | "删除晚安模式" |
| `HassListVoiceScenes` | 列出所有语音场景 | "我有哪些语音场景？" |

## 支持的平台

- `assist_satellite` - 语音助手卫星
- `conversation` - 对话集成（LLM）
- `stt` - 语音转文字
- `tts` - 文字转语音
- `climate` - 空调控制
- `select` - 选择器
- `sensor` - 传感器
- `switch` - 开关
- `light` - 灯光
- `button` - 按钮
- `binary_sensor` - 二进制传感器
- `cover` - 窗帘/卷帘
- `fan` - 风扇
- `lock` - 锁
- `media_player` - 媒体播放器
- `number` - 数字输入
- `valve` - 阀门
- `alarm_control_panel` - 报警控制面板

## 版本要求

- Home Assistant 最新版本
- Python 3.13+
- ESPHome 设备

## 安装

### 方法一：通过 HACS 安装（推荐）

1. 确保已安装 [HACS](https://hacs.xyz/)
2. 在 HACS 中添加自定义仓库：`https://github.com/huijian/huijian-ai-ha`
3. 搜索并安装 `huijian AI`
4. 重启 Home Assistant

### 方法二：手动安装

1. 下载或克隆此仓库
2. 将 `huijian_ai` 文件夹复制到 Home Assistant 的 `custom_components` 目录下
3. 重启 Home Assistant

## 配置

### 通过界面配置

1. 进入 Home Assistant 的 **设置** → **设备与服务**
2. 点击 **添加集成**
3. 搜索并选择 **huijian AI**
4. 按照配置向导完成设置

### 二维码配网

集成支持通过二维码快速配置 ESPHome 设备：

1. 在配置界面选择二维码配网方式
2. 使用 ESPHome 设备扫描显示的二维码
3. 等待设备连接并自动配置

### 手动配置

```yaml
# configuration.yaml (如需要)
huijian_ai:
```

## 与 ESPHome 设备配合使用

此集成需要配合运行相应固件的 ESPHome 设备使用。设备需要：

1. 安装 ESPHome 固件
2. 启用以下功能：
   - Native API（原生 API）
   - ESPHome Voice Assistant 组件（可选，用于语音助手）
   - 加密密钥（推荐）

### ESPHome 配置示例

```yaml
esphome:
  name: my-voice-assistant
  friendly_name: 我的语音助手

api:
  encryption:
    key: "your-encryption-key-here"

wifi:
  ssid: "Your WiFi SSID"
  password: "Your WiFi Password"

ota:
  - platform: esphome

voice_assistant:
  microphone: your-microphone-component
  speaker: your-speaker-component
```

## 依赖

- `aioesphomeapi>=42.9.1`
- `esphome-dashboard-api>=1.3.0`
- `bleak-esphome>=3.4.0`
- `opuslib_next>=1.0.0`

## 项目结构

```
huijian_ai/
├── __init__.py              # 主入口
├── manifest.json             # 集成清单
├── config_flow.py            # 配置流程
├── const.py                  # 常量定义
├── api.py                    # API 相关
├── intent.py                 # 意图处理
├── coordinator.py            # 数据协调器
├── manager.py                # 设备管理器
├── websocket_api.py          # WebSocket API
├── huijian/                  # 核心模块
│   ├── __init__.py
│   ├── audio.py              # 音频处理
│   ├── http.py               # HTTP 服务
│   ├── llm_transport.py      # LLM 传输
│   ├── mcp_transport.py      # MCP 传输
│   ├── stt_transport.py      # STT 传输
│   ├── tts_transport.py      # TTS 传输
│   └── ws_transport.py       # WebSocket 传输
├── translations/             # 国际化翻译
│   ├── en.json               # 英文
│   └── zh-Hans.json          # 简体中文
└── brand/                    # 品牌资源
```

## 支持的 ESPHome 设备

此集成设计用于与以下类型的 ESPHome 设备配合使用：

- ESP32 / ESP32-S3 开发板
- ESP32 蓝牙代理
- 支持语音功能的自定义设备

## 文档

- [GitHub 仓库](https://github.com/huijian/huijian-ai-ha)
- [问题反馈](https://github.com/huijian/huijian-ai-ha/issues)

## 致谢

此集成基于 ESPHome 项目构建，使用了以下开源库：

- [aioesphomeapi](https://github.com/esphome/aioesphomeapi) - ESPHome API Python 客户端
- [ESPHome](https://esphome.io/) - ESP32/ESP8266 的编程框架

## 许可证

本项目采用 MIT 许可证。

## 版本历史

- **2026.1.3** - 最新版本，支持完整的语音助手功能
