# GitHub 发布与 Actions 问题记录

本文档记录 GitHub 发布和 Actions 工作流中遇到的常见问题及解决方案。

---

## 1. GitHub Actions Workflow 问题

### 问题 1: Hassfest 验证超时/失败

**症状**: workflow 运行失败，提示克隆 home-assistant/core 超时

**原因分析**:
- 克隆完整的大型仓库 (`home-assistant/core`) 耗时过长
- 网络问题导致克隆失败
- Python 依赖 `voluptuous` 安装可能失败

**发生时间**: 2026-03-05

**解决方案**: 
简化 workflow，仅保留 HACS 验证（推荐）

```yaml
# ✅ 推荐配置 - 只保留 HACS 验证
name: Validate
on:
  push:
  pull_request:

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: HACS validation
        uses: hacs/action@main
        with:
          category: integration
```

**避免事项**:
- ❌ 不要使用 `hacs/action@main` 以外的复杂验证
- ❌ 不要克隆完整仓库（如 home-assistant/core）
- ❌ 不要安装不必要的 Python 依赖用于验证

---

### 问题 2: Workflow 合并冲突

**症状**: 本地分支与远程分支 divergence，出现合并冲突

**原因**:
- 本地提交与远程提交互相独立
- 多次重置或强制推送导致

**解决方案**:
```bash
# 方法 1: 拉取远程最新并合并
git pull --rebase

# 方法 2: 如果本地有重要更改，先 stash
git stash
git pull --rebase
git stash pop

# 方法 3: 放弃本地更改，同步远程（慎用）
git fetch origin
git reset --hard origin/main
```

---

### 问题 3: Git Push 失败 - 网络连接问题

**症状**: `Failed to connect to github.com port 443`

**解决方案**:
- 检查网络连接
- 稍后重试
- 考虑使用 VPN

---

## 2. HACS 提交问题

### 问题: SUBMIT_BRANDS_GUIDE.md 临时文件

**症状**: 仓库中残留已完成的指导文档

**解决方案**:
- 完成后及时删除临时文档
- 使用有意义的 commit message

```bash
git rm SUBMIT_BRANDS_GUIDE.md
git commit -m "chore: remove SUBMIT_BRANDS_GUIDE.md (completed)"
git push
```

---

## 3. 最佳实践

1. **Workflow 简化原则**: 只保留必要的验证步骤
2. **及时清理**: 完成后删除临时文件和文档
3. **网络检查**: 推送前确认网络连接正常
4. **版本控制**: 使用稳定版本的 action（如 `@main` 或具体版本标签）

---

## 更新日志

- 2026-03-05: 初始记录 - 添加 Hassfest 验证问题和解决方案
