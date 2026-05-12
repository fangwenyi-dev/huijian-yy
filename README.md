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
- **语音场景**：支持创建语音触发的场景（如"当我说晚安时，帮我关灯"）
- **传感器自动化**：支持创建传感器条件自动化（如"温度大于29度开窗"）
- **管理页面**：集成管理页面，支持场景/自动化的增删改查
- **LLM 容错**：自动修正 LLM 传入的错误域名和设备 ID

## 支持的意图

集成通过 MCP 协议自动暴露以下意图工具，支持与小智服务器等 LLM 系统集成。

### 设备控制

| 意图名称 | 说明 | 示例语音 |
|---------|------|---------|
| `TurnDeviceOn` | 打开设备 | "打开卧室灯"、"打开客厅空调"、"打开窗户" |
| `TurnDeviceOff` | 关闭设备 | "关闭卧室灯"、"关闭电视"、"关闭窗户" |

### 设备调节

| 意图名称 | 属性 | 支持平台 | 示例语音 |
|---------|------|---------|---------|
| `AdjustDeviceAttribute` | `brightness` | 灯光 | "灯调亮一点"、"亮度调到50%" |
| `AdjustDeviceAttribute` | `color` | 灯光 | "灯调成蓝色"、"颜色改成#FF0000" |
| `AdjustDeviceAttribute` | `temperature` | 灯光、空调 | "色温调高一点"、"温度调到26度" |
| `AdjustDeviceAttribute` | `fan_speed` | 风扇、空调 | "风速调大一档" |
| `AdjustDeviceAttribute` | `humidity` | 加湿器、除湿器 | "湿度调到60%" |
| `AdjustDeviceAttribute` | `position` | 窗帘、窗户 | "窗帘开50%"、"窗户关一半" |

### 模式设置

| 意图名称 | 说明 | 支持平台 | 示例语音 |
|---------|------|---------|---------|
| `SetDeviceMode` | 设置设备模式 | 空调、加湿器 | "空调调到制冷模式"、"加湿器调到静音模式" |

### 窗户控制

| 意图名称 | 说明 | 示例语音 |
|---------|------|---------|
| `TurnDeviceOn` (cover) | 通过 cover 域打开窗户 | "打开客厅窗户"、"打开平开窗"、"打开推拉窗" |
| `TurnDeviceOff` (cover) | 通过 cover 域关闭窗户 | "关闭卧室窗户"、"关闭天窗" |
| `ControlWindow` | 通过按钮控制窗户（特殊协议） | "平推窗暂停" |
| `AdjustDeviceAttribute` | 调节窗户位置 | "窗户开50%" |

### 实时上下文

| 意图名称 | 说明 | 用途 |
|---------|------|------|
| `huijianGetLiveContext` | 获取实时设备状态 | 用于回答"灯开着吗？"、"现在温度多少？"等问题 |

### 语音场景

| 意图名称 | 说明 | 示例语音 |
|---------|------|---------|
| `HassCreateVoiceScene` | 创建语音场景（语音触发） | "当我说'晚安'的时候，帮我关灯并锁门" |
| `HassTriggerVoiceScene` | 触发语音场景 | "晚安" |
| `HassDeleteVoiceScene` | 删除语音场景 | "删除晚安场景" |
| `HassListVoiceScenes` | 列出所有语音场景 | "我有哪些语音场景？" |
| `HassUpdateVoiceScene` | 更新语音场景 | "把晚安场景改为先关灯后关门" |

### 传感器自动化

| 意图名称 | 说明 | 示例语音 |
|---------|------|---------|
| `HassCreateAutomation` | 创建传感器条件自动化 | "当温度大于29度就打开卧室窗户" |
| `HassDeleteAutomation` | 删除自动化 | "删除自动化" |
| `HassListAutomations` | 列出所有自动化 | "有哪些自动化？" |
| `HassUpdateAutomation` | 更新自动化条件或动作 | "把自动化的阈值改为30度" |

### 其他工具

| 意图名称 | 说明 | 用途 |
|---------|------|------|
| `HassBroadcast` | 广播消息 | TTS 语音广播 |
| `GetDateTime` | 获取日期时间 | "现在几点了？" |
| `HassCancelAllTimers` | 取消所有定时器 | "取消所有定时" |
| `HassClimateSetTemperature` | 设置空调温度 | "空调温度设为24度" |

## LLM 容错机制

集成内置多层容错机制，确保 LLM 在各种输入偏差下仍能正确执行：

### 域名别名映射
LLM 可能使用非标准域名，系统自动映射到 HA 实际域名：

| LLM 传入域名 | 映射到 HA 域 | 说明 |
|-------------|------------|------|
| `window` / `windows` | `cover` | 窗户在 HA 中为 cover 域 |
| `curtain` / `curtains` | `cover` | 窗帘在 HA 中为 cover 域 |
| `blind` / `blinds` | `cover` | 百叶帘在 HA 中为 cover 域 |
| `shutter` / `shutters` | `cover` | 卷帘在 HA 中为 cover 域 |
| `plug` / `plugs` | `switch` | 插座在 HA 中为 switch 域 |
| `outlet` / `outlets` | `switch` | 插座在 HA 中为 switch 域 |

### 三级匹配通道
实体查找按优先级依次尝试：
1. **严格匹配**：按 LLM 指定域名 + 名称 + 区域 + 助手过滤
2. **宽松匹配**：去掉助手过滤，匹配所有暴露设备
3. **device_class 兜底**：当域名匹配失败时，按 device_class 搜索所有非传感器实体

### 传感器自动修正
`HassCreateAutomation` 创建自动化时，如果 LLM 传入的传感器 entity_id 不存在，自动搜索 HA 中匹配的传感器（支持 22 种 device_class，中英文关键词匹配）。

## 支持的设备类型

| domain | 设备类型 | 支持的操作 |
|--------|---------|-----------|
| `light` | 灯、筒灯、主灯、台灯、吊灯、灯带、户外灯 | 开关、亮度、颜色 |
| `cover` | 窗帘、窗户、电动窗帘、卷帘、百叶帘 | 开关、位置 |
| `climate` | 空调 | 开关、温度、模式 |
| `switch` | 开关、插座、电脑、显示器、咖啡机 | 开关 |
| `lock` | 门锁 | 开关 |
| `valve` | 阀门 | 开关 |
| `fan` | 风扇、排风扇 | 开关、风速 |
| `humidifier` | 加湿器、除湿器 | 开关、湿度 |
| `media_player` | 电视、音响、投影仪、播放器 | 开关 |
| `alarm_control_panel` | 报警控制面板 | 布防/撤防 |
| `vacuum` | 扫地机器人、吸尘器 | 开始/回充 |
| `water_heater` | 热水器 | 开关、模式 |
| `sensor` | 温度、湿度、光照等传感器 | 自动化触发条件 |
| `binary_sensor` | 门窗磁、人体传感器等 | 自动化触发条件 |

## 管理页面

集成提供 Web 管理页面，可统一管理语音场景和传感器自动化：

- **访问地址**：`http://{HA地址}/huijian-ai/manage`
- **功能列表**：
  - 查看所有语音场景和传感器自动化
  - 创建、编辑、删除场景和自动化
  - 一键测试场景/自动化触发
  - 查看自动化触发日志（自动刷新）
- **配置集成后**：通过集成配置页面的"管理场景和自动化"按钮也可以进入

## 支持的区域

卧室、主卧、次卧、老人房、儿童房、客厅、厨房、书房、餐厅、浴室、卫生间、玄关、走廊、阳台、储物间、地下室、车库、车间、办公室、展厅、小展厅、室外、影音室、茶室、棋牌室、健身房、娱乐室、露台、杂物间、保姆房、酒窖、洗衣房等。

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
2. 在 HACS 中添加自定义仓库：`https://github.com/fangwenyi-dev/huijian-yy`
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
├── __init__.py                    # 主入口
├── manifest.json                   # 集成清单
├── config_flow.py                  # 配置流程
├── const.py                        # 常量定义
├── api.py                          # REST API + 管理页面
├── intent.py                       # 意图注册
├── coordinator.py                  # 数据协调器
├── manager.py                      # ESPHome 设备管理器
├── websocket_api.py                # WebSocket API
├── intent_helper.py                # 实体匹配核心（域名别名 + device_class 兜底）
├── intent_turn.py                  # TurnDeviceOn/Off 执行器
├── intent_window_control.py        # ControlWindow 意图
├── intent_window_const.py          # 窗户常量定义
├── intent_adjust_attribute.py      # AdjustDeviceAttribute 意图
├── intent_set_mode.py              # SetDeviceMode 意图
├── intent_automation.py            # 传感器自动化系统（Store + Manager + 5 个意图）
├── intent_voice_scene.py           # 语音场景系统（Store + 5 个意图）
├── intent_live_context.py          # huijianGetLiveContext 意图
├── intent_device_shared.py         # 设备识别共享模块
├── huijian/                        # 核心模块
│   ├── __init__.py
│   ├── audio.py                    # 音频处理
│   ├── http.py                     # HTTP 服务
│   ├── llm_transport.py            # LLM 传输
│   ├── mcp_transport.py            # MCP 传输
│   ├── stt_transport.py            # STT 传输
│   ├── tts_transport.py            # TTS 传输
│   └── ws_transport.py             # WebSocket 传输
├── translations/                   # 国际化翻译
│   ├── en.json                     # 英文
│   └── zh-Hans.json                # 简体中文
└── brand/                          # 品牌资源
```

## 支持的 ESPHome 设备

此集成设计用于与以下类型的 ESPHome 设备配合使用：

- ESP32 / ESP32-S3 开发板
- ESP32 蓝牙代理
- 支持语音功能的自定义设备

## 文档

- [GitHub 仓库](https://github.com/fangwenyi-dev/huijian-yy)
- [问题反馈](https://github.com/fangwenyi-dev/huijian-yy/issues)

## 致谢

此集成基于 ESPHome 项目构建，使用了以下开源库：

- [aioesphomeapi](https://github.com/esphome/aioesphomeapi) - ESPHome API Python 客户端
- [ESPHome](https://esphome.io/) - ESP32/ESP8266 的编程框架

## 许可证

本项目采用 MIT 许可证。

## 版本历史

- **1.2.0** - 新增 LLM 容错机制（域名别名映射 + device_class 兜底 + 22 种传感器修正）、管理页面触发日志 + 一键测试、新增设备类型（alarm/vacuum/water_heater/climate）
- **1.1.0** - 新增传感器自动化系统（HassCreateAutomation/UpdateAutomation）、触发日志、管理页面
- **1.0.0** - 初始版本发布