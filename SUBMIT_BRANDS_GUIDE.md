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

4. **提交 Pull Request**
   - 点击 "Commit changes"
   - 创建 Pull Request

### 方法2：通过命令行提交

```bash
# 1. Fork 后克隆
git clone https://github.com/YOUR_USERNAME/brands
cd brands

# 2. 创建文件夹并复制文件
mkdir -p custom_integrations/window_controller_gateway
cp /path/to/icon.png custom_integrations/window_controller_gateway/
cp /path/to/icon@2x.png custom_integrations/window_controller_gateway/
cp /path/to/logo.png custom_integrations/window_controller_gateway/

# 3. 提交并推送
git add .
git commit -m "Add Huijian Window Controller Gateway brand icons"
git push origin master

# 4. 在 GitHub 网页创建 Pull Request
```

---

## 替代方案：使用本地图标（推荐）

由于 HA 2026.3.0+，自定义集成可以直接包含品牌图标。你当前的配置已经是正确的：

```json
"brand": {
  "name": "Huijian",
  "manufacturer": "Huijian Intelligent Technology",
  "images": {
    "icon": "brand/icon.png",
    "logo": "brand/logo.png"
  }
}
```

图标文件已复制到：
- `\\100.70.165.93\config\www\window_controller_gateway\`

等待 HA 缓存刷新（最多7天），图标将自动显示。

---

## 总结

| 方案 | 优点 | 缺点 |
|------|------|------|
| 提交到官方仓库 | 全球 CDN 加速 | 需要准备正确尺寸的图标 |
| 使用本地图标 | 立即生效 | 依赖本地文件加载 |

**建议**：先修复图标尺寸问题，然后提交到官方仓库获得最佳体验。
