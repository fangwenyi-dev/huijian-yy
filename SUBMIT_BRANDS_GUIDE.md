# 提交到 home-assistant/brands 仓库指南

## 图标要求

根据 [home-assistant/brands](https://github.com/home-assistant/brands) 官方文档：

### icon.png
- 尺寸：256x256 像素
- 比例：1:1 (正方形)
- 格式：PNG

### icon@2x.png
- 尺寸：512x512 像素
- 比例：1:1 (正方形)
- 格式：PNG

### logo.png (可选)
- 最短边：128-256 像素
- 格式：PNG

---

## 当前文件问题

你的当前图标尺寸：382x360 (不是正方形)

需要重新制作：
1. `icon.png` → 裁剪/调整为 256x256 正方形
2. `icon@2x.png` → 制作 512x512 版本
3. `logo.png` → 保持原样或调整

---

## 提交步骤

### 方法1：通过 GitHub 网页提交（推荐）

1. **Fork 仓库**
   - 打开 https://github.com/home-assistant/brands
   - 点击右上角 "Fork"

2. **创建文件夹**
   - 进入 `custom_integrations` 目录
   - 创建新文件夹：`window_controller_gateway`

3. **上传图标**
   - 上传 `icon.png` (256x256)
   - 上传 `icon@2x.png` (512x512)
   - 上传 `logo.png` (可选)
