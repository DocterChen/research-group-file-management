# 科研成果管理小程序

微信小程序前端，用于科研成果管理平台的移动端访问。

## 功能特性

### 核心功能
- ✅ 微信登录（支持 UnionID 统一身份）
- ✅ 课题组绑定（加入现有课题组 / 创建新课题组）
- ✅ 成果列表查看（搜索、筛选、分页）
- ✅ 成果详情查看
- ✅ 成果提交审核
- ✅ 管理员审核工作台（通过/退回）
- ✅ 仪表盘统计（总成果数、已审核、待审核、草稿）
- ✅ 个人中心（用户信息、课题组信息、邀请码管理）

### 用户角色
- **管理员/PI**：可查看邀请码、审核成果、管理课题组
- **成员**：可查看成果、提交成果、编辑自己的草稿

### 成果类型
- 论文
- 专利
- 软件著作权
- 会议成果
- 项目/基金材料
- 数据与代码

## 技术栈

- **框架**：微信小程序原生框架（WXML + WXSS + JavaScript）
- **后端 API**：RESTful API (http://localhost:8080/api/v1/*)
- **会话管理**：session_token 存储在本地缓存
- **UI 设计**：参考现有 web.py 视觉语言（主色：#0ea5e9）

## 目录结构

```
miniprogram/
├── app.js                      # 应用入口，全局状态管理
├── app.json                    # 全局配置（页面路由、tabBar、窗口样式）
├── app.wxss                    # 全局样式
├── pages/                      # 页面
│   ├── login/                  # 登录页
│   ├── bind/                   # 绑定课题组页
│   ├── dashboard/              # 仪表盘
│   ├── outputs/                # 成果列表
│   ├── output-detail/          # 成果详情
│   └── profile/                # 个人中心
├── utils/                      # 工具函数
│   ├── api.js                  # API 请求封装
│   ├── auth.js                 # 认证工具函数
│   └── format.js               # 格式化工具函数
├── components/                 # 自定义组件（预留）
└── assets/                     # 静态资源（图标、图片）
```

## 快速开始

### 前置条件

1. 安装[微信开发者工具](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html)
2. 后端 API 服务已启动（默认：http://localhost:8080）
3. 获取微信小程序 AppID 和 AppSecret

### 配置后端 API

后端需要完成以下配置：

1. 在 `.env` 或 `config.yaml` 中配置微信小程序凭证：

```yaml
wechat:
  miniprogram:
    appid: "your_miniprogram_appid"
    secret: "your_miniprogram_secret"
```

2. 启动后端 API 服务：

```bash
# 开发环境
python api_server.py

# 生产环境（需要 HTTPS）
gunicorn -w 4 -b 0.0.0.0:8080 api_server:app
```

### 配置小程序

1. 修改 `app.js` 中的 API 地址：

```javascript
// 开发环境（使用内网穿透或本地调试）
apiBase: 'http://localhost:8080/api/v1'

// 生产环境（必须使用 HTTPS）
apiBase: 'https://your-domain.com/api/v1'
```

2. 在微信公众平台配置服务器域名白名单：
   - 登录 [微信公众平台](https://mp.weixin.qq.com/)
   - 开发 → 开发管理 → 开发设置 → 服务器域名
   - 添加 `https://your-domain.com`

### 运行小程序

1. 打开微信开发者工具
2. 选择"导入项目"
3. 选择 `miniprogram` 目录
4. 输入 AppID（或使用测试号）
5. 点击"编译"运行

### 本地调试（不验证域名）

开发阶段可以关闭域名验证：

1. 微信开发者工具 → 右上角"详情"
2. 本地设置 → 勾选"不校验合法域名..."
3. 这样就可以访问 `http://localhost:8080` 进行调试

## API 接口

### 认证接口

#### POST /api/v1/wechat/miniprogram/login
微信小程序登录

**请求体**：
```json
{
  "code": "wx.login() 返回的 code"
}
```

**响应**：
```json
// 登录成功
{
  "status": "success",
  "session_token": "...",
  "csrf_token": "...",
  "username": "...",
  "display_name": "...",
  "lab_id": "...",
  "role": "admin"
}

// 需要绑定课题组
{
  "status": "need_bind",
  "unionid": "...",
  "openid": "...",
  "session_key": "..."
}
```

#### POST /api/v1/wechat/bind
绑定课题组

**请求体**（加入现有课题组）：
```json
{
  "unionid": "...",
  "openid": "...",
  "source": "miniprogram",
  "invite_code": "ABC123",
  "display_name": "张三"
}
```

**请求体**（创建新课题组）：
```json
{
  "unionid": "...",
  "openid": "...",
  "source": "miniprogram",
  "create_lab": true,
  "lab_name": "张三课题组",
  "lab_subtitle": "人工智能研究团队",
  "display_name": "张三"
}
```

### 成果接口

#### GET /api/v1/outputs
获取成果列表

**查询参数**：
- `page`: 页码（默认 1）
- `limit`: 每页数量（默认 20）
- `search`: 搜索关键词
- `type`: 成果类型筛选
- `status`: 状态筛选

**响应**：
```json
{
  "outputs": [
    {
      "output_id": "LW20260715001",
      "title": "深度学习在医学影像中的应用",
      "output_type": "article",
      "review_status": "approved",
      "authors": ["张三", "李四"],
      "created_at": "2026-07-15T10:00:00Z",
      "updated_at": "2026-07-15T12:00:00Z"
    }
  ],
  "total": 42,
  "page": 1,
  "limit": 20
}
```

#### GET /api/v1/outputs/:output_id
获取成果详情

#### POST /api/v1/outputs/:output_id/submit
提交审核

#### POST /api/v1/outputs/:output_id/approve
审核通过（管理员）

#### POST /api/v1/outputs/:output_id/return
退回成果（管理员）

#### DELETE /api/v1/outputs/:output_id
删除成果（草稿状态）

### 仪表盘接口

#### GET /api/v1/dashboard/stats
获取统计数据

**响应**：
```json
{
  "total": 42,
  "approved": 30,
  "submitted": 5,
  "draft": 7
}
```

## 部署说明

### 开发环境部署

1. 使用内网穿透工具（如 [natapp](https://natapp.cn/)）暴露本地后端：
   ```bash
   ./natapp -authtoken=your_token
   ```

2. 在小程序 `app.js` 中配置穿透后的 HTTPS 地址：
   ```javascript
   apiBase: 'https://abc123.natappfree.cc/api/v1'
   ```

### 生产环境部署

1. **后端部署**：
   - 部署到云服务器（阿里云、腾讯云等）
   - 配置 Nginx 反向代理
   - 配置 HTTPS 证书（Let's Encrypt）

2. **小程序配置**：
   - 修改 `app.js` 中的 `apiBase` 为生产环境地址
   - 在微信公众平台配置服务器域名白名单
   - 提交代码审核

3. **微信小程序审核**：
   - 登录微信公众平台
   - 版本管理 → 上传代码
   - 提交审核（需提供功能说明和测试账号）

## 常见问题

### 1. 登录后提示"网络请求失败"
- 检查后端 API 是否正常运行
- 检查 `app.js` 中的 `apiBase` 配置是否正确
- 开发阶段确保已关闭域名校验

### 2. 提示"Invalid or expired session"
- session_token 已过期（默认 8 小时）
- 重新登录即可

### 3. 无法获取 UnionID
- 确保公众号和小程序已绑定到同一个微信开放平台账号
- 或者用户已关注同主体的公众号

### 4. 小程序审核不通过
- 确保功能描述清晰
- 提供完整的测试账号和使用说明
- 避免违规内容（广告、支付等）

## 功能扩展

### 待开发功能（可选）
- [ ] 成果新增/编辑表单
- [ ] 附件上传和预览
- [ ] 成果导出（Excel）
- [ ] 消息推送（审核通知）
- [ ] 数据可视化（统计图表）
- [ ] 成员管理
- [ ] 项目管理

### 组件化（预留目录）
- `components/output-card`：成果卡片组件
- `components/stat-card`：统计卡片组件
- `components/filter-bar`：筛选栏组件

## 许可证

本项目遵循项目根目录的许可协议。

## 相关文档

- [微信小程序官方文档](https://developers.weixin.qq.com/miniprogram/dev/framework/)
- [后端 API 文档](../docs/plans/wechat-miniprogram-multilab.md)
- [项目指令文档](../AGENTS.md)

## 联系方式

如有问题，请通过以下方式联系：
- 提交 Issue
- 查看项目文档
