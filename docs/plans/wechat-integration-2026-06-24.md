# 科研成果管理软件 - 微信集成方案

> **制定时间：** 2026-06-24  
> **目标：** 让课题组成员通过微信便捷访问和使用系统

---

## 📋 方案总览

| 方案 | 实施难度 | 开发时间 | 用户体验 | 推荐度 |
|------|---------|---------|---------|--------|
| **方案 1：微信内网页访问** | ⭐ 极简单 | 0 天（已支持） | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ 强烈推荐 |
| **方案 2：微信登录集成** | ⭐⭐ 简单 | 1-2 天 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **方案 3：微信小程序** | ⭐⭐⭐⭐ 复杂 | 2-4 周 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **方案 4：企业微信集成** | ⭐⭐⭐ 中等 | 1 周 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐（企业场景） |

---

## 🎯 方案 1：微信内网页访问（立即可用）

### 现状分析

✅ **已支持功能：**
- 移动端视口配置（`viewport` meta 标签）
- 响应式设计（`@media` 查询）
- 移动端友好的 CSS（最大宽度限制、自适应布局）

✅ **兼容性：**
- 微信内置浏览器（基于 X5 内核）
- iOS 微信浏览器
- Android 微信浏览器

### 实施步骤（0 开发成本）

#### 步骤 1：确保 HTTPS 部署
```bash
# 使用 Cloudflare Tunnel（已在部署脚本中）
cloudflared tunnel run research-manager

# 访问地址自动为 HTTPS
https://research.your-domain.com
```

**为什么需要 HTTPS？**
- 微信要求网页必须使用 HTTPS
- 文件上传、定位等功能需要 HTTPS

#### 步骤 2：优化微信分享卡片
在 `web.py` 的 `<head>` 标签中添加：

```html
<!-- 微信分享优化 -->
<meta property="og:title" content="课题组科研成果管理软件" />
<meta property="og:description" content="文献、专利、项目统一管理平台" />
<meta property="og:image" content="https://research.your-domain.com/logo.png" />
<meta property="og:url" content="https://research.your-domain.com" />

<!-- 微信特有标签 -->
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-status-bar-style" content="black" />
<meta name="apple-mobile-web-app-title" content="成果管理" />
```

#### 步骤 3：添加"添加到桌面"引导
在首次访问时显示提示：

```html
<!-- 添加到桌面引导提示 -->
<div id="add-to-home-tip" style="display:none; position:fixed; bottom:60px; left:50%; transform:translateX(-50%); background:#fff; padding:15px 20px; border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.15); z-index:9999;">
  <p style="margin:0; font-size:14px; color:#333;">
    💡 提示：点击右上角 <strong>···</strong> → <strong>在浏览器打开</strong> → <strong>添加到桌面</strong>
    <br>下次可以像小程序一样打开
  </p>
  <button onclick="document.getElementById('add-to-home-tip').style.display='none'" style="margin-top:10px; padding:6px 12px; background:#0ea5e9; color:#fff; border:none; border-radius:6px; cursor:pointer;">知道了</button>
</div>

<script>
// 首次访问时显示提示
if (!localStorage.getItem('hideAddToHomeTip')) {
  setTimeout(() => {
    document.getElementById('add-to-home-tip').style.display = 'block';
  }, 2000);
  
  // 用户点击"知道了"后不再显示
  window.addEventListener('click', (e) => {
    if (e.target.textContent === '知道了') {
      localStorage.setItem('hideAddToHomeTip', 'true');
    }
  });
}
</script>
```

#### 步骤 4：创建微信分享引导文档

**给课题组成员的使用指南：**

```markdown
# 如何在微信中使用科研成果管理软件

## 方式 1：直接访问（推荐）

1. 扫描二维码或点击链接：https://research.your-domain.com
2. 首次需要登录（账号由管理员分配）
3. 使用完毕后可以添加到微信收藏

## 方式 2：添加到桌面（类似小程序体验）

### iOS 用户：
1. 在微信中打开系统链接
2. 点击右上角 **···**
3. 选择 **在 Safari 中打开**
4. 点击底部 **分享** 图标
5. 选择 **添加到主屏幕**
6. 点击 **添加**

### Android 用户：
1. 在微信中打开系统链接
2. 点击右上角 **···**
3. 选择 **在浏览器打开**
4. 点击浏览器菜单
5. 选择 **添加到主屏幕**

## 常见问题

### Q1：为什么有些功能不能用？
A：确保使用 HTTPS 访问，并授权浏览器权限（如文件上传）

### Q2：可以离线使用吗？
A：不可以。需要联网访问。

### Q3：数据安全吗？
A：是的。使用 HTTPS 加密传输，服务器在课题组内部。
```

---

## 🔐 方案 2：微信登录集成（扫码登录）

### 实现方式

#### 选项 A：微信开放平台登录（需要网站应用）

**前提条件：**
- 注册微信开放平台账号（https://open.weixin.qq.com/）
- 通过开发者资质认证（企业：¥300/年）
- 创建"网站应用"并获得 AppID 和 AppSecret

**实施步骤：**

1. **在登录页添加"微信登录"按钮**
```python
# 在 web.py 中添加微信登录路由
def handle_wechat_login(self):
    """处理微信登录请求"""
    app_id = "your_wechat_app_id"
    redirect_uri = quote("https://research.your-domain.com/wechat-callback")
    state = secrets.token_urlsafe(16)
    
    # 保存 state 到 session
    self.set_session_value("wechat_state", state)
    
    # 跳转到微信授权页面
    auth_url = f"https://open.weixin.qq.com/connect/qrconnect?appid={app_id}&redirect_uri={redirect_uri}&response_type=code&scope=snsapi_login&state={state}#wechat_redirect"
    
    self.send_response(302)
    self.send_header("Location", auth_url)
    self.end_headers()

def handle_wechat_callback(self):
    """处理微信回调"""
    query = parse_qs(urlparse(self.path).query)
    code = query.get("code", [""])[0]
    state = query.get("state", [""])[0]
    
    # 验证 state
    saved_state = self.get_session_value("wechat_state")
    if state != saved_state:
        return self.send_error_page("微信登录失败：state 验证失败")
    
    # 使用 code 换取 access_token
    token_url = f"https://api.weixin.qq.com/sns/oauth2/access_token?appid={app_id}&secret={app_secret}&code={code}&grant_type=authorization_code"
    response = requests.get(token_url)
    data = response.json()
    
    if "access_token" not in data:
        return self.send_error_page("微信登录失败：获取 access_token 失败")
    
    access_token = data["access_token"]
    openid = data["openid"]
    
    # 获取用户信息
    user_info_url = f"https://api.weixin.qq.com/sns/userinfo?access_token={access_token}&openid={openid}"
    user_response = requests.get(user_info_url)
    user_data = user_response.json()
    
    # 查找或创建用户（需要在数据库中存储 openid 与用户账号的映射）
    # 这里需要扩展 Member 模型添加 wechat_openid 字段
    member = self.find_member_by_wechat_openid(openid)
    
    if not member:
        # 首次微信登录，需要绑定已有账号或创建新账号
        return self.send_binding_page(openid, user_data)
    
    # 创建 session
    self.create_session(member.member_id)
    
    # 跳转到首页
    self.send_redirect("/")
```

2. **在登录页添加微信登录按钮**
```html
<div class="login-box">
  <h2>登录</h2>
  
  <!-- 原有的账号密码登录 -->
  <form method="post">
    <input type="text" name="username" placeholder="用户名" />
    <input type="password" name="password" placeholder="密码" />
    <button type="submit">登录</button>
  </form>
  
  <!-- 分隔线 -->
  <div style="text-align:center; margin:20px 0;">
    <span style="color:#999;">或</span>
  </div>
  
  <!-- 微信登录按钮 -->
  <a href="/wechat-login" style="display:block; padding:12px; background:#07c160; color:#fff; text-align:center; border-radius:6px; text-decoration:none;">
    <svg style="width:20px; height:20px; vertical-align:middle; margin-right:8px;" viewBox="0 0 24 24">
      <!-- 微信图标 SVG -->
    </svg>
    微信扫码登录
  </a>
</div>
```

3. **扩展 Member 模型添加微信绑定字段**
```python
@dataclass
class Member:
    member_id: str
    name: str
    role: Role
    email: str = ""
    notes: str = ""
    wechat_openid: str = ""  # 新增：微信 OpenID
    wechat_unionid: str = ""  # 新增：微信 UnionID（如果有多个应用）
```

**成本分析：**
- 微信开放平台认证：¥300/年（企业）
- 开发时间：1-2 天
- 维护成本：低

#### 选项 B：公众号登录（免费）

如果课题组有微信公众号（订阅号或服务号），可以使用公众号网页授权：

**前提条件：**
- 认证的服务号或订阅号
- 配置 JS 接口安全域名

**优势：**
- 完全免费
- 静默授权（用户无感知）
- 获取用户微信昵称、头像

**实施步骤：** 类似选项 A，但使用公众号的 AppID 和 授权接口

---

## 📱 方案 3：微信小程序（原生体验）

### 架构设计

```
微信小程序前端（WXML + JS）
        ↓
    REST API（改造后端）
        ↓
   ResearchRepository（复用现有逻辑）
        ↓
    JSON 数据存储
```

### 开发任务拆解

#### 阶段 1：后端 API 化（1 周）

**任务 1.1：创建独立的 API 模块**
```python
# src/lab_literature_manager/api.py
from flask import Flask, jsonify, request
from .repository import ResearchRepository
from .permissions import can_perform

app = Flask(__name__)
repo = ResearchRepository("data/local")

@app.route("/api/login", methods=["POST"])
def api_login():
    """用户登录"""
    data = request.json
    # 验证用户名密码
    # 返回 JWT token
    return jsonify({"token": "...", "user": {...}})

@app.route("/api/members", methods=["GET"])
def api_list_members():
    """获取成员列表"""
    token = request.headers.get("Authorization")
    # 验证 token
    members = repo.list_members()
    return jsonify([m.__dict__ for m in members])

@app.route("/api/outputs", methods=["GET", "POST"])
def api_outputs():
    """成果管理"""
    if request.method == "GET":
        outputs = repo.list_outputs()
        return jsonify([o.__dict__ for o in outputs])
    else:
        data = request.json
        # 创建成果
        return jsonify({"success": True})

# ... 更多 API 端点
```

**任务 1.2：添加 JWT 认证**
```python
import jwt
from datetime import datetime, timedelta

SECRET_KEY = "your-secret-key"

def generate_token(member_id):
    """生成 JWT token"""
    payload = {
        "member_id": member_id,
        "exp": datetime.utcnow() + timedelta(hours=8)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def verify_token(token):
    """验证 JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload["member_id"]
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
```

#### 阶段 2：小程序前端开发（2-3 周）

**任务 2.1：注册小程序账号**
- 访问：https://mp.weixin.qq.com/
- 注册类型：企业/组织（需要营业执照或组织机构代码证）
- 费用：¥300 认证费（首次）

**任务 2.2：开发小程序页面**

**目录结构：**
```
miniprogram/
├── pages/
│   ├── index/           # 首页（成果列表）
│   ├── login/           # 登录页
│   ├── member/          # 成员管理
│   ├── project/         # 项目管理
│   ├── output-detail/   # 成果详情
│   └── output-edit/     # 成果编辑
├── utils/
│   ├── api.js          # API 封装
│   └── auth.js         # 认证逻辑
├── app.js              # 小程序入口
├── app.json            # 全局配置
└── app.wxss            # 全局样式
```

**核心代码示例：**

```javascript
// utils/api.js
const API_BASE = "https://research.your-domain.com/api";

function request(url, method = "GET", data = null) {
  const token = wx.getStorageSync("token");
  
  return new Promise((resolve, reject) => {
    wx.request({
      url: API_BASE + url,
      method: method,
      data: data,
      header: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      success: (res) => {
        if (res.statusCode === 200) {
          resolve(res.data);
        } else {
          reject(res);
        }
      },
      fail: reject
    });
  });
}

// 导出 API 方法
module.exports = {
  login: (username, password) => request("/login", "POST", {username, password}),
  getMembers: () => request("/members"),
  getOutputs: () => request("/outputs"),
  createOutput: (data) => request("/outputs", "POST", data),
  // ... 更多 API
};
```

```javascript
// pages/index/index.js
const api = require("../../utils/api");

Page({
  data: {
    outputs: []
  },
  
  onLoad() {
    this.loadOutputs();
  },
  
  async loadOutputs() {
    wx.showLoading({ title: "加载中..." });
    try {
      const outputs = await api.getOutputs();
      this.setData({ outputs });
    } catch (error) {
      wx.showToast({ title: "加载失败", icon: "none" });
    } finally {
      wx.hideLoading();
    }
  },
  
  onOutputTap(e) {
    const outputId = e.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/output-detail/index?id=${outputId}`
    });
  }
});
```

```xml
<!-- pages/index/index.wxml -->
<view class="container">
  <view class="header">
    <text class="title">科研成果管理</text>
  </view>
  
  <view class="output-list">
    <block wx:for="{{outputs}}" wx:key="output_id">
      <view class="output-item" bindtap="onOutputTap" data-id="{{item.output_id}}">
        <view class="output-title">{{item.title}}</view>
        <view class="output-meta">
          <text class="type">{{item.output_type}}</text>
          <text class="year">{{item.year}}</text>
          <text class="status">{{item.review_status}}</text>
        </view>
      </view>
    </block>
  </view>
  
  <view class="add-button" bindtap="onAddTap">
    <text>+</text>
  </view>
</view>
```

**任务 2.3：微信登录集成**
```javascript
// pages/login/index.js
Page({
  async onWechatLogin() {
    try {
      // 1. 获取微信授权码
      const { code } = await wx.login();
      
      // 2. 发送到后端换取 token
      const res = await wx.request({
        url: "https://research.your-domain.com/api/wechat-login",
        method: "POST",
        data: { code }
      });
      
      // 3. 保存 token
      wx.setStorageSync("token", res.data.token);
      
      // 4. 跳转到首页
      wx.switchTab({ url: "/pages/index/index" });
    } catch (error) {
      wx.showToast({ title: "登录失败", icon: "none" });
    }
  }
});
```

#### 阶段 3：发布上线（1-2 天）

1. 提交代码审核
2. 等待微信审核（1-7 天）
3. 审核通过后发布
4. 设置体验版供内部测试

**开发成本总结：**
- 小程序认证费：¥300/年
- 开发时间：2-4 周
- 后续维护：每周 2-4 小时

---

## 🏢 方案 4：企业微信集成（企业场景）

### 适用条件

- 学校/研究所已使用企业微信
- 需要与组织架构同步
- 需要审批流程集成

### 实施步骤

#### 步骤 1：注册企业微信应用
1. 访问：https://work.weixin.qq.com/
2. 管理后台 → 应用管理 → 创建应用
3. 配置应用主页 URL：`https://research.your-domain.com`

#### 步骤 2：配置单点登录
```python
# 企业微信 OAuth2.0 登录
def handle_work_wechat_login(self):
    corp_id = "your_corp_id"
    agent_id = "your_agent_id"
    redirect_uri = "https://research.your-domain.com/work-wechat-callback"
    
    auth_url = f"https://open.weixin.qq.com/connect/oauth2/authorize?appid={corp_id}&redirect_uri={redirect_uri}&response_type=code&scope=snsapi_base&agentid={agent_id}#wechat_redirect"
    
    self.send_redirect(auth_url)
```

#### 步骤 3：同步组织架构
```python
# 从企业微信同步成员信息
def sync_members_from_work_wechat():
    access_token = get_work_wechat_access_token()
    
    # 获取部门列表
    dept_url = f"https://qyapi.weixin.qq.com/cgi-bin/department/list?access_token={access_token}"
    depts = requests.get(dept_url).json()
    
    # 获取成员列表
    for dept in depts["department"]:
        user_url = f"https://qyapi.weixin.qq.com/cgi-bin/user/simplelist?access_token={access_token}&department_id={dept['id']}"
        users = requests.get(user_url).json()
        
        for user in users["userlist"]:
            # 创建或更新成员
            member = Member(
                member_id=user["userid"],
                name=user["name"],
                role=Role.MEMBER,
                email=user.get("email", "")
            )
            repo.add_or_update_member(member)
```

#### 步骤 4：消息推送
```python
# 审批通过后推送企业微信消息
def send_work_wechat_message(user_id, content):
    access_token = get_work_wechat_access_token()
    
    message_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
    
    data = {
        "touser": user_id,
        "msgtype": "text",
        "agentid": agent_id,
        "text": {
            "content": content
        }
    }
    
    requests.post(message_url, json=data)

# 使用示例
def approve_output(output_id, approver_id):
    output = repo.get_output(output_id)
    # 更新状态
    output.review_status = ReviewStatus.APPROVED
    repo.update_output(output)
    
    # 推送消息给提交人
    send_work_wechat_message(
        output.owner_member_ids[0],
        f"您提交的成果《{output.title}》已通过审核"
    )
```

---

## 🎯 推荐实施路线图

### 第 1 周：立即可用（方案 1）
```bash
1. 完成系统部署（已有脚本）
2. 配置 Cloudflare Tunnel（HTTPS）
3. 优化微信分享卡片
4. 编写用户使用指南
5. 发送链接给课题组成员
```

**成果：** 所有人都能在微信中使用

---

### 第 2-3 周：体验提升（方案 2）
```bash
1. 注册微信开放平台（如需要）
2. 集成微信登录
3. 添加账号绑定功能
4. 测试登录流程
```

**成果：** 扫码登录，无需记密码

---

### 第 4-8 周：原生体验（方案 3，可选）
```bash
1. 后端 API 化改造
2. 开发微信小程序
3. 提交审核
4. 发布上线
```

**成果：** 类似原生 App 的体验

---

## 💰 成本对比

| 方案 | 开发成本 | 年度费用 | 总成本/年 |
|------|---------|---------|----------|
| **方案 1：网页访问** | ¥0 | ¥50（域名） | ¥50 |
| **方案 2：微信登录** | 1-2 天 | ¥300（认证） | ¥300 |
| **方案 3：小程序** | 2-4 周 | ¥300（认证） | ¥300 + 开发成本 |
| **方案 4：企业微信** | 1 周 | ¥0（已有企业微信） | ¥0 |

---

## ✅ 立即可执行：方案 1 优化

我可以立即为您：

### 1. 优化 web.py 添加微信分享支持
- 添加 Open Graph 标签
- 添加"添加到桌面"引导
- 优化移动端显示

### 2. 生成用户使用指南
- 如何在微信中访问
- 如何添加到桌面
- 常见问题解答

### 3. 创建二维码和分享卡片
- 生成系统访问二维码
- 设计微信分享图片

---

**您想要哪种方案？**
1. 立即优化方案 1（微信内网页访问）- 今天就能用
2. 规划方案 2（微信登录集成）- 下周实施
3. 了解方案 3（小程序开发）- 长期规划
4. 考虑方案 4（企业微信）- 如果有企业微信

请告诉我您的选择，我立即开始执行！🚀
