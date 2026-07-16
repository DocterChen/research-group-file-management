# 微信小程序开发指南

## 初次打开项目

1. **安装微信开发者工具**
   - 下载地址：https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html

2. **准备图标资源**
   - 查看 `assets/icons/README.md` 了解所需图标
   - 可以先使用纯文字 TabBar 进行开发（见下方说明）

3. **配置后端 API 地址**
   - 编辑 `app.js`，修改 `apiBase` 为实际后端地址
   - 开发环境：`http://localhost:8080/api/v1`
   - 生产环境：`https://your-domain.com/api/v1`

4. **启动后端服务**
   ```bash
   cd ..
   python api_server.py
   ```

5. **打开小程序项目**
   - 用微信开发者工具导入本目录
   - AppID：使用测试号或正式 AppID
   - 开启"不校验合法域名"选项（本地开发时）

## 临时解决方案：无图标启动

如果暂时没有图标资源，可以修改 `app.json` 的 `tabBar` 配置：

```json
{
  "tabBar": {
    "color": "#666666",
    "selectedColor": "#0ea5e9",
    "backgroundColor": "#ffffff",
    "borderStyle": "black",
    "list": [
      {
        "pagePath": "pages/dashboard/dashboard",
        "text": "仪表盘"
      },
      {
        "pagePath": "pages/outputs/outputs",
        "text": "成果管理"
      },
      {
        "pagePath": "pages/profile/profile",
        "text": "我的"
      }
    ]
  }
}
```

移除所有 `iconPath` 和 `selectedIconPath` 字段即可使用纯文字 TabBar。

## 快速生成占位图标（macOS/Linux）

如果安装了 ImageMagick，可以快速生成占位图标：

```bash
cd assets/icons

# 生成 TabBar 图标
convert -size 81x81 xc:#6b7280 dashboard.png
convert -size 81x81 xc:#0ea5e9 dashboard-active.png
convert -size 81x81 xc:#6b7280 outputs.png
convert -size 81x81 xc:#0ea5e9 outputs-active.png
convert -size 81x81 xc:#6b7280 profile.png
convert -size 81x81 xc:#0ea5e9 profile-active.png

# 生成其他图标
convert -size 200x200 xc:#0ea5e9 ../logo.png
convert -size 48x48 xc:#07c160 wechat.png
convert -size 120x120 xc:#9ca3af ../avatar.png
```

## 开发调试

1. **查看网络请求**
   - 微信开发者工具 → 调试器 → Network
   - 检查 API 请求和响应

2. **查看 Console 日志**
   - 微信开发者工具 → 调试器 → Console
   - 查看 `console.log` 和错误信息

3. **真机调试**
   - 微信开发者工具 → 工具栏 → 预览
   - 扫码在手机上调试

## 常见问题

1. **提示"不在以下 request 合法域名列表中"**
   - 开发阶段：开启"不校验合法域名"
   - 生产阶段：在微信公众平台配置服务器域名白名单

2. **登录失败**
   - 检查后端 API 是否正常运行
   - 检查微信小程序配置（AppID、AppSecret）是否正确

3. **样式显示异常**
   - 检查 rpx 单位是否使用正确
   - 清除缓存重新编译

## 下一步

完成开发后，参考 `README.md` 的"部署说明"部分进行生产环境部署。
