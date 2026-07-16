# 微信小程序 API 集成文档

本文档说明如何使用已集成到 web.py 的微信小程序 API。

## 概述

微信小程序 API 已成功集成到现有的 Web 服务器中，支持：

- 小程序登录认证
- 多课题组管理
- 成果数据访问
- CORS 支持

## 配置

### 1. 创建 .env 文件

在项目根目录创建 `.env` 文件：

```bash
# 微信小程序
WECHAT_MINIPROGRAM_APPID=your_miniprogram_appid
WECHAT_MINIPROGRAM_SECRET=your_miniprogram_secret

# 微信公众号
WECHAT_OFFICIALACCOUNT_APPID=your_officialaccount_appid
WECHAT_OFFICIALACCOUNT_SECRET=your_officialaccount_secret

# 数据目录
DATA_DIR=data/local

# 服务器配置
SERVER_HOST=0.0.0.0
SERVER_PORT=8080
```

### 2. 启动服务器

```bash
# 使用示例脚本
python api_server_example.py

# 或使用现有的 web.py
python -m lab_literature_manager.web
```

服务器将监听 `http://0.0.0.0:8080`

## API 端点

### 认证相关

#### 1. 小程序登录

```http
POST /api/v1/wechat/miniprogram/login
Content-Type: application/json

{
  "code": "wx.login() 返回的 code"
}
```

**响应（已登录用户）：**
```json
{
  "status": "success",
  "session_token": "...",
  "csrf_token": "...",
  "username": "wechat_xxx",
  "display_name": "用户名",
  "lab_id": "lab_xxx",
  "role": "member"
}
```

**响应（需要绑定）：**
```json
{
  "status": "need_bind",
  "unionid": "...",
  "openid": "...",
  "session_key": "..."
}
```

#### 2. 绑定课题组

```http
POST /api/v1/wechat/bind
Content-Type: application/json

# 创建新课题组
{
  "openid": "...",
  "unionid": "...",
  "source": "miniprogram",
  "create_lab": true,
  "lab_name": "课题组名称",
  "lab_subtitle": "副标题",
  "display_name": "用户姓名"
}

# 或加入现有课题组
{
  "openid": "...",
  "unionid": "...",
  "source": "miniprogram",
  "invite_code": "邀请码",
  "display_name": "用户姓名"
}
```

**响应：**
```json
{
  "status": "success",
  "session_token": "...",
  "csrf_token": "...",
  "lab_id": "lab_xxx",
  "lab_name": "课题组名称",
  "invite_code": "ABCD1234"
}
```

### 课题组管理

#### 3. 列出课题组

```http
GET /api/v1/labs
X-Session-Token: <session_token>
```

**响应：**
```json
{
  "labs": [
    {
      "lab_id": "lab_xxx",
      "lab_name": "课题组名称",
      "lab_subtitle": "副标题",
      "role": "admin"
    }
  ]
}
```

#### 4. 获取课题组信息

```http
GET /api/v1/labs/:lab_id
X-Session-Token: <session_token>
```

**响应：**
```json
{
  "lab_id": "lab_xxx",
  "lab_name": "课题组名称",
  "lab_subtitle": "副标题",
  "created_at": "2026-07-16T10:00:00+00:00",
  "invite_code": "ABCD1234"
}
```

#### 5. 重新生成邀请码

```http
POST /api/v1/labs/:lab_id/regenerate_invite_code
X-Session-Token: <session_token>
```

**响应：**
```json
{
  "invite_code": "EFGH5678"
}
```

### 成果管理

#### 6. 获取成果列表

```http
GET /api/v1/outputs?page=1&page_size=20&search=&type=&status=
X-Session-Token: <session_token>
```

**查询参数：**
- `page`: 页码（默认 1）
- `page_size`: 每页条数（默认 20）
- `search`: 搜索关键词
- `type`: 成果类型（article, patent, software_copyright 等）
- `status`: 审核状态（draft, submitted, approved, returned, archived）

**响应：**
```json
{
  "outputs": [
    {
      "output_id": "LW-2026-001",
      "title": "成果标题",
      "output_type": "article",
      "output_type_label": "文章",
      "review_status": "approved",
      "review_status_label": "已通过",
      "year": 2026,
      "summary": "摘要..."
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 50,
    "total_pages": 3
  }
}
```

#### 7. 获取成果详情

```http
GET /api/v1/outputs/:output_id
X-Session-Token: <session_token>
```

**响应：**
```json
{
  "output_id": "LW-2026-001",
  "title": "成果标题",
  "output_type": "article",
  "output_type_label": "文章",
  "review_status": "approved",
  "review_status_label": "已通过",
  "year": 2026,
  "summary": "摘要...",
  "notes": "备注...",
  "keywords": ["关键词1", "关键词2"],
  "owner_member_ids": ["member1", "member2"],
  "participant_member_ids": ["member3"],
  "project_ids": ["project1"],
  "created_at": "2026-07-16T10:00:00+00:00",
  "updated_at": "2026-07-16T12:00:00+00:00",
  "article": {
    "article_type": "research_article",
    "journal": "Nature",
    "doi": "10.1038/xxx",
    "pmid": "12345678",
    "issn": "0028-0836",
    "publication_year": 2026,
    "submission_status": "已发表",
    "first_authors": ["张三", "李四", "王五"]
  }
}
```

## CORS 支持

所有 API 端点都支持 CORS，允许小程序跨域访问：

```http
OPTIONS /api/v1/*
```

**响应头：**
```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization, X-Session-Token
Access-Control-Max-Age: 86400
```

## 认证流程

1. 小程序调用 `wx.login()` 获取 `code`
2. 将 `code` 发送到 `POST /api/v1/wechat/miniprogram/login`
3. 如果返回 `status: "success"`，保存 `session_token` 用于后续请求
4. 如果返回 `status: "need_bind"`，引导用户绑定课题组
5. 用户选择创建新课题组或使用邀请码加入
6. 调用 `POST /api/v1/wechat/bind` 完成绑定
7. 保存返回的 `session_token` 用于后续请求

## 会话管理

- 所有需要认证的 API 都需要在请求头中包含 `X-Session-Token`
- Session 默认有效期为 8 小时
- Session 会在每次请求时自动续期

## 错误处理

**错误响应格式：**
```json
{
  "error": "错误信息"
}
```

**常见错误：**
- `400 Bad Request`: 请求参数错误
- `401 Unauthorized`: 未登录或 session 过期
- `403 Forbidden`: 权限不足
- `404 Not Found`: 资源不存在
- `500 Internal Server Error`: 服务器内部错误

## 测试

### 单元测试

```bash
# 测试多课题组功能
python -m unittest tests.test_multilab -v

# 测试 API 集成
python -m unittest tests.test_api_integration -v
```

### API 测试客户端

```bash
# 启动服务器
python api_server_example.py

# 在另一个终端运行测试客户端
python test_api_client.py
```

## 小程序端示例代码

```javascript
// 1. 登录
wx.login({
  success: (res) => {
    wx.request({
      url: 'http://your-server:8080/api/v1/wechat/miniprogram/login',
      method: 'POST',
      data: {
        code: res.code
      },
      success: (res) => {
        if (res.data.status === 'success') {
          // 保存 session_token
          wx.setStorageSync('session_token', res.data.session_token);
          // 跳转到首页
          wx.switchTab({ url: '/pages/index/index' });
        } else if (res.data.status === 'need_bind') {
          // 跳转到绑定页面
          wx.navigateTo({ 
            url: '/pages/bind/bind?openid=' + res.data.openid 
          });
        }
      }
    });
  }
});

// 2. 获取成果列表
wx.request({
  url: 'http://your-server:8080/api/v1/outputs',
  method: 'GET',
  header: {
    'X-Session-Token': wx.getStorageSync('session_token')
  },
  success: (res) => {
    console.log(res.data.outputs);
  }
});
```

## 架构说明

### 集成方式

微信小程序 API 已集成到现有的 `web.py` 中，使用以下组件：

1. **MultiLabRepository**: 管理多个课题组的数据隔离
2. **WeChatConfig**: 微信配置（从 .env 加载）
3. **APIRequestHandler**: API 请求处理逻辑
4. **LocalWebRequestHandler**: HTTP 请求路由

### 数据隔离

每个课题组的数据存储在独立目录：

```
data/local/
├── labs.json               # 课题组注册表
├── lab_<id1>/             # 课题组1
│   ├── members.json
│   ├── projects.json
│   ├── research_outputs.json
│   └── users.json
└── lab_<id2>/             # 课题组2
    └── ...
```

### 权限控制

- **ADMIN/PI**: 可以管理课题组、审核成果、重新生成邀请码
- **MEMBER**: 可以查看和提交成果
- 所有用户只能访问自己所属课题组的数据

## 故障排查

### API 未初始化

如果看到 `{"error": "API not configured"}`，检查：

1. `.env` 文件是否存在且格式正确
2. 微信配置是否填写
3. `config.py` 是否正确加载配置

### 循环导入错误

如果遇到循环导入，确保：

1. `api_extensions.py` 不从 `web.py` 导入 `WebUser`
2. `api_extensions.py` 已定义自己的 `WebUser` 类

### CORS 问题

如果小程序无法访问 API：

1. 确保小程序后台配置了服务器域名
2. 确保服务器支持 HTTPS（生产环境）
3. 检查 CORS 响应头是否正确

## 相关文档

- [wechat-miniprogram-multilab.md](docs/plans/wechat-miniprogram-multilab.md) - 技术方案
- [wechat-implementation-summary.md](docs/plans/wechat-implementation-summary.md) - 实施总结
