# HACS 品牌目录提交流入指南

## 当前状态

你的集成 `慧尖开窗器网关` (window_controller_gateway) 已满足以下 HACS 要求：

✅ **manifest.json** - 已包含必要字段
- domain: window_controller_gateway
- documentation
- issue_tracker (使用 GitHub)
- codeowners
- name
- version: 1.2.2.2

✅ **hacs.json** - 已配置
- name: 慧尖开窗器网关
- country: CN
- domains: cover, binary_sensor, button, sensor

✅ **品牌信息** - 已在 manifest.json 中配置
- brand.name: 慧尖
- brand.manufacturer: Huijian Intelligent Technology

✅ **图标** - 已准备
- icons/icon.png
- icons/icon@2x.png
- icons/logo.png

---

## 提交到 HACS 默认仓库

由于 MCP GitHub 工具权限不足，请按以下步骤手动操作：

### 步骤 1: Fork HACS 默认仓库

1. 打开 https://github.com/hacs/default
2. 点击右上角的 "Fork" 按钮
3. 选择你的账户进行 Fork

### 步骤 2: 添加你的集成

1. 打开你 Fork 的仓库
2. 进入 `integrations` 文件夹
3. 创建一个新文件，命名为 `window_controller_gateway.json`
4. 添加以下内容：

```json
{
  "name": "慧尖开窗器网关",
  "country": "CN",
  "homeassistant": "2024.0.0",
  "domains": [
    "cover",
    "binary_sensor",
    "button",
    "sensor"
  ]
}
```

5. 提交更改 (Commit)

### 步骤 3: 创建 Pull Request

1. 点击 "Contribute" 按钮
2. 点击 "Open Pull Request"
3. 填写标题: "Add window_controller_gateway integration"
4. 提交 Pull Request

---

## 同时提交到 Home Assistant 品牌目录

### 步骤 1: Fork brands 仓库

1. 打开 https://github.com/home-assistant/brands
2. Fork 到你的账户

### 步骤 2: 添加品牌信息

1. 进入 `brands` 文件夹
2. 创建一个新文件，命名为 `huijian.json`:
```json
{
  "name": "慧尖",
  "manufacturer": "Huijian Intelligent Technology",
  "model": "慧尖开窗器网关",
  "integrations": [
    "window_controller_gateway"
  ]
}
```

3. 进入 `icons` 文件夹，添加品牌图标
4. 提交并创建 Pull Request

---

## 参考链接

- HACS 默认仓库: https://github.com/hacs/default
- Home Assistant 品牌: https://github.com/home-assistant/brands
- HACS 文档: https://hacs.xyz/docs/publish/integration
