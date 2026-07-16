# 图标占位说明

本目录用于存放小程序所需的图标资源。

## 所需图标列表

### TabBar 图标（必需）
由于微信小程序 TabBar 必须使用本地图片，需要准备以下图标（建议尺寸：81x81px）：

1. **dashboard.png** - 仪表盘图标（未选中状态）
2. **dashboard-active.png** - 仪表盘图标（选中状态）
3. **outputs.png** - 成果管理图标（未选中状态）
4. **outputs-active.png** - 成果管理图标（选中状态）
5. **profile.png** - 我的图标（未选中状态）
6. **profile-active.png** - 我的图标（选中状态）

### 其他图标（可选）
- **logo.png** - 应用 Logo（登录页使用，建议 200x200px）
- **wechat.png** - 微信图标（登录按钮使用，48x48px）
- **avatar.png** - 默认头像（个人中心使用，120x120px）

## 快速生成占位图标

### 方法 1：使用在线工具
- 访问 [iconfont](https://www.iconfont.cn/) 或 [Flaticon](https://www.flaticon.com/)
- 搜索对应图标并下载 PNG 格式

### 方法 2：使用纯色占位
开发阶段可以使用纯色方块作为占位图标：

```bash
# macOS / Linux（需要 ImageMagick）
convert -size 81x81 xc:#0ea5e9 dashboard.png
convert -size 81x81 xc:#0284c7 dashboard-active.png
convert -size 81x81 xc:#6b7280 outputs.png
convert -size 81x81 xc:#0ea5e9 outputs-active.png
convert -size 81x81 xc:#6b7280 profile.png
convert -size 81x81 xc:#0ea5e9 profile-active.png
```

### 方法 3：临时修改配置
如果暂时没有图标，可以注释掉 `app.json` 中的 `tabBar.list[].iconPath` 和 `selectedIconPath` 字段，使用纯文字 TabBar：

```json
{
  "tabBar": {
    "list": [
      {
        "pagePath": "pages/dashboard/dashboard",
        "text": "仪表盘"
      }
    ]
  }
}
```

## 设计建议

- **风格统一**：使用线性图标或面性图标，保持统一风格
- **颜色规范**：
  - 未选中状态：#6b7280（灰色）
  - 选中状态：#0ea5e9（主题蓝色）
- **尺寸规范**：TabBar 图标 81x81px，其他图标根据使用场景调整
- **格式要求**：PNG 格式，支持透明背景
