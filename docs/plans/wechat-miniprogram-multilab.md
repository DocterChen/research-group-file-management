# 微信小程序接入与多课题组支持 - 技术方案大纲

**制定日期**：2026-07-15  
**状态**：规划阶段  
**目标**：将现有科研成果管理软件接入微信小程序，并支持多课题组独立登录和数据隔离

---

## 一、核心需求

### 1.1 微信小程序接入
- 提供微信小程序前端，替代或补充现有 Web UI
- 支持课题组成员通过微信小程序完成成果录入、审核、查看统计等核心功能
- 保持与现有 Web UI 的功能对等性

### 1.2 多课题组支持
- 支持多个课题组独立注册和管理
- 每个课题组拥有独立的成员、项目、成果数据
- 课题组之间数据完全隔离，互不可见
- 每个课题组可独立设置管理员、PI 和成员

### 1.3 微信公众号对接（新增需求）
- 课题组已有微信公众号，需要与小程序无缝对接
- 用户可从公众号菜单/文章/消息直接跳转到小程序
- 实现公众号与小程序的用户身份互通

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────┐      ┌─────────────────┐
│ 微信公众号平台  │      │  微信小程序前端  │
│  (菜单/文章)    │◄────►│   (WXML/WXSS)   │
└────────┬────────┘      └────────┬────────┘
         │                        │ HTTPS
         └────────────┬───────────┘
                      ↓
              ┌─────────────────┐
              │   后端 API 层    │
              │  (Flask/FastAPI)│
              └────────┬────────┘
                       │
                  ┌────┴────┐
                  ↓         ↓
              ┌────────┐ ┌──────────┐
              │数据存储 │ │微信服务API│
              │(升级版) │ │ (登录等)  │
              └────────┘ └──────────┘
```

**说明**：
- 公众号与小程序共享后端 API 和数据存储
- 用户身份通过微信 UnionID 统一（公众号和小程序属于同一主体）
- 公众号菜单可直接跳转小程序特定页面

### 2.2 架构演进路径

#### 阶段一：最小改动（推荐优先实现）
- 保持现有 `web.py` 的单机架构
- 新增 RESTful API 端点供小程序调用
- 数据存储仍使用多文件 JSON 结构
- 通过 `lab_id` 字段区分不同课题组

#### 阶段二：服务化改造（可选，长期演进）
- 将 `web.py` 拆分为独立的 API 服务（Flask/FastAPI）
- 引入关系型数据库（SQLite → PostgreSQL）
- 支持云端部署和多实例负载均衡
- 完整的微服务架构

**本大纲重点关注阶段一，确保最小改动、最快落地。**

---

## 三、认证与授权体系

### 3.1 微信登录集成

#### 微信小程序登录流程
```
1. 小程序调用 wx.login() 获取临时 code
2. 小程序将 code 发送到后端 /api/wechat/login
3. 后端用 code + appid + secret 调用微信 API 换取 openid/session_key
4. 后端检查 openid 是否已绑定用户：
   - 已绑定：返回自定义 session token
   - 未绑定：返回"需要绑定"状态，引导用户选择课题组并输入邀请码/注册
5. 小程序存储 session token，后续请求携带该 token
```

#### 微信公众号登录流程（新增）
```
1. 用户在公众号内点击菜单/文章链接
2. 跳转到授权页面，引导用户授权获取 openid
3. 后端通过 OAuth2.0 网页授权获取用户 openid（静默授权 or 用户信息授权）
4. 如果需要跳转小程序：
   方案A：使用微信 URL Scheme 唤起小程序（需要服务端生成）
   方案B：使用公众号菜单直接配置小程序跳转（推荐）
5. 如果在公众号内操作：返回 H5 页面，功能同小程序
```

#### UnionID 机制（关键）
**前提**：公众号和小程序必须绑定到同一个微信开放平台账号

```python
# 用户身份统一识别
@dataclass(frozen=True)
class WebUser:
    username: str
    password_hash: str  # 可选，微信登录时为空
    password_salt: str
    display_name: str
    role: Role
    member_id: str = ""
    lab_id: str = ""  # 新增：课题组 ID
    wechat_openid: str = ""  # 微信 openid（小程序或公众号）
    wechat_unionid: str = ""  # 新增：微信 UnionID（同一主体下唯一）
    wechat_source: str = ""  # 新增：来源（miniprogram/official_account）
    created_at: str = ""
    account_status: str = ACCOUNT_STATUS_ACTIVE
```

**UnionID 作用**：
- 同一用户在公众号和小程序中的 openid 不同，但 unionid 相同
- 后端以 unionid 为主键，实现跨平台身份识别
- 用户在公众号登录后，进入小程序无需重新登录

### 3.2 多课题组隔离

#### 课题组模型
```python
@dataclass(frozen=True)
class Lab:
    lab_id: str  # 唯一标识
    lab_name: str  # 课题组名称
    lab_subtitle: str  # 副标题
    created_at: str
    admin_usernames: List[str]  # 管理员列表
    invite_code: str = ""  # 邀请码（可选）
    settings: Dict[str, Any] = field(default_factory=dict)
```

#### 数据目录结构演进
```
data/local/
├── labs.json  # 新增：课题组注册表
├── lab_<lab_id_1>/
│   ├── members.json
│   ├── projects.json
│   ├── research_outputs.json
│   ├── users.json
│   └── workspace_settings.json
├── lab_<lab_id_2>/
│   ├── members.json
│   ├── ...
└── ...
```

### 3.3 权限检查增强

所有 API 请求必须携带：
- `session_token`：验证用户身份
- `lab_id`：从 session 中提取，确保用户只能访问自己所属课题组的数据

权限检查流程：
```
1. 解析 session_token → 获取 username 和 lab_id
2. 验证用户是否属于请求的 lab_id
3. 加载该 lab_id 对应的 repository
4. 执行现有权限检查逻辑（can_perform）
```

---

## 四、后端 API 设计

### 4.1 API 端点规划

#### 认证与课题组管理
```
POST   /api/wechat/login          # 微信登录
POST   /api/wechat/bind            # 绑定课题组
POST   /api/labs/register          # 注册新课题组
GET    /api/labs/list              # 列出用户可访问的课题组
POST   /api/labs/switch            # 切换当前课题组
```

#### 成果管理（需要 lab_id 上下文）
```
GET    /api/outputs                # 成果列表
POST   /api/outputs                # 新增成果
GET    /api/outputs/:id            # 成果详情
PUT    /api/outputs/:id            # 编辑成果
DELETE /api/outputs/:id            # 删除成果
POST   /api/outputs/:id/submit     # 提交审核
POST   /api/outputs/:id/approve    # 审核通过
POST   /api/outputs/:id/return     # 退回
POST   /api/outputs/:id/archive    # 归档
```

#### 成员与项目管理
```
GET    /api/members                # 成员列表
POST   /api/members                # 新增成员
GET    /api/projects               # 项目列表
POST   /api/projects               # 新增项目
```

#### 统计与导出
```
GET    /api/dashboard/stats        # 仪表盘统计
GET    /api/exports/excel          # Excel 导出
```

#### 外部数据抓取
```
POST   /api/fetch/doi              # DOI 抓取
POST   /api/fetch/pubmed           # PubMed 抓取
POST   /api/fetch/patent           # 专利抓取
POST   /api/fetch/document         # 文档上传识别
```

### 4.2 API 实现策略

#### 方案 A：扩展现有 `web.py`（推荐）
- 在 `WebRequestHandler` 中新增 `/api/*` 路由
- 复用现有的 `ResearchRepository`、权限检查逻辑
- 返回 JSON 格式数据（去除 HTML 渲染）
- 优点：改动最小，快速上线
- 缺点：单机架构，无法水平扩展

#### 方案 B：独立 API 服务（长期）
- 使用 Flask 或 FastAPI 构建独立 API 服务
- 将 `models.py`、`repository.py`、`permissions.py` 抽取为共享库
- 优点：架构清晰，易于扩展
- 缺点：需要较大重构

**本阶段推荐方案 A，先快速验证需求，后续再考虑方案 B。**

---

## 五、数据存储升级

### 5.1 多课题组数据隔离

#### 存储结构调整
```python
class MultiLabRepository:
    """管理多课题组的数据访问"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.labs_file = base_dir / "labs.json"
        self._lab_repos: Dict[str, ResearchRepository] = {}
    
    def get_lab_repo(self, lab_id: str) -> ResearchRepository:
        """获取指定课题组的 repository"""
        if lab_id not in self._lab_repos:
            lab_dir = self.base_dir / f"lab_{lab_id}"
            self._lab_repos[lab_id] = ResearchRepository(str(lab_dir))
        return self._lab_repos[lab_id]
    
    def create_lab(self, lab: Lab) -> None:
        """创建新课题组"""
        lab_dir = self.base_dir / f"lab_{lab.lab_id}"
        lab_dir.mkdir(parents=True, exist_ok=True)
        # 初始化空数据文件
        # ...
    
    def list_labs(self) -> List[Lab]:
        """列出所有课题组"""
        # ...
```

### 5.2 数据迁移脚本

现有单课题组数据需要迁移到多课题组结构：
```python
def migrate_to_multilab(old_data_dir: Path, new_data_dir: Path, default_lab_id: str):
    """
    迁移现有数据到多课题组结构
    1. 创建默认课题组目录
    2. 移动所有数据文件到 lab_<default_lab_id>/
    3. 生成 labs.json
    """
    pass
```

---

## 六、微信公众号与小程序对接方案

### 12.1 对接模式选择

#### 模式 A：公众号菜单跳转小程序（推荐）
**优点**：
- 配置简单，无需开发
- 用户体验流畅，直接唤起小程序
- 可跳转到小程序任意页面

**实现步骤**：
1. 在微信公众平台后台配置关联小程序
2. 自定义菜单设置 `miniprogram` 类型
3. 配置小程序 AppID 和跳转路径

```json
// 公众号菜单配置示例
{
  "button": [
    {
      "type": "miniprogram",
      "name": "成果管理",
      "url": "http://mp.weixin.qq.com",  // 备用网页链接
      "appid": "wx1234567890abcdef",     // 小程序 AppID
      "pagepath": "pages/dashboard/index" // 跳转路径
    },
    {
      "name": "快捷入口",
      "sub_button": [
        {
          "type": "miniprogram",
          "name": "录入成果",
          "appid": "wx1234567890abcdef",
          "pagepath": "pages/output-form/index"
        },
        {
          "type": "miniprogram",
          "name": "审核工作台",
          "appid": "wx1234567890abcdef",
          "pagepath": "pages/review/index"
        }
      ]
    }
  ]
}
```

#### 模式 B：公众号文章/消息中插入小程序卡片
**优点**：
- 可在推文中嵌入小程序入口
- 支持多样化的内容营销

**实现方式**：
- 编辑图文消息时插入小程序卡片
- 可自定义卡片标题、封面图
- 点击卡片直接跳转小程序

#### 模式 C：URL Scheme 唤起小程序
**优点**：
- 可从短信、邮件、外部网页唤起
- 适合生成动态跳转链接

**实现步骤**：
1. 后端调用微信 API 生成 URL Scheme
2. 链接有效期最长 30 天
3. 用户点击链接唤起小程序

```python
# 后端生成 URL Scheme 示例
import requests

def generate_wechat_scheme(access_token: str, page_path: str, query: str = "") -> str:
    """
    生成微信小程序 URL Scheme
    :param access_token: 小程序 access_token
    :param page_path: 跳转页面路径
    :param query: 页面参数
    :return: scheme URL
    """
    url = "https://api.weixin.qq.com/wxa/generatescheme"
    params = {"access_token": access_token}
    data = {
        "jump_wxa": {
            "path": page_path,
            "query": query
        },
        "expire_type": 0,  # 到期失效
        "expire_interval": 30  # 30天后失效
    }
    resp = requests.post(url, params=params, json=data)
    return resp.json().get("openlink", "")
```

#### 模式 D：公众号 H5 页面 + 小程序互通
**优点**：
- 公众号内也可操作，无需跳转
- 适合不方便使用小程序的场景

**架构**：
```
公众号菜单
    ↓
H5 页面（响应式 Web UI）
    ↓
后端 API（与小程序共用）
```

### 12.2 UnionID 统一身份方案（核心）

#### 前置条件
- 公众号和小程序必须绑定到同一个微信开放平台账号
- 开放平台账号需完成开发者资质认证

#### 绑定流程
```
1. 登录微信开放平台 (open.weixin.qq.com)
2. 创建/进入开放平台账号
3. 管理中心 → 公众账号/小程序 → 绑定公众号和小程序
4. 绑定成功后，同一用户在两个平台的 UnionID 相同
```

#### 身份识别逻辑
```python
def get_or_create_user_by_wechat(unionid: str, openid: str, source: str) -> WebUser:
    """
    根据 UnionID 获取或创建用户
    :param unionid: 微信 UnionID
    :param openid: 当前平台的 OpenID
    :param source: 来源（miniprogram/official_account）
    """
    # 1. 先查找是否存在该 unionid 的用户
    user = find_user_by_unionid(unionid)
    
    if user:
        # 2. 存在则更新对应平台的 openid
        if source == "miniprogram" and not user.wechat_miniprogram_openid:
            user = update_user_openid(user, miniprogram_openid=openid)
        elif source == "official_account" and not user.wechat_officialaccount_openid:
            user = update_user_openid(user, officialaccount_openid=openid)
        return user
    
    # 3. 不存在则创建新用户（引导绑定课题组）
    return create_pending_user(unionid, openid, source)
```

#### 数据模型完整版
```python
@dataclass(frozen=True)
class WebUser:
    username: str
    password_hash: str = ""  # 可选，微信登录时为空
    password_salt: str = ""
    display_name: str = ""
    role: Role = Role.MEMBER
    member_id: str = ""
    lab_id: str = ""
    
    # 微信身份字段（扩展）
    wechat_unionid: str = ""  # UnionID（跨平台唯一）
    wechat_miniprogram_openid: str = ""  # 小程序 OpenID
    wechat_officialaccount_openid: str = ""  # 公众号 OpenID
    wechat_nickname: str = ""  # 微信昵称（可选）
    wechat_avatar: str = ""  # 微信头像（可选）
    
    created_at: str = ""
    account_status: str = ACCOUNT_STATUS_ACTIVE
```

### 12.3 公众号菜单配置实战

#### 配置示例（完整菜单结构）
```json
{
  "button": [
    {
      "type": "miniprogram",
      "name": "进入小程序",
      "url": "https://your-domain.com/h5/dashboard",  // 不支持小程序时的备用链接
      "appid": "wx1234567890abcdef",
      "pagepath": "pages/dashboard/index"
    },
    {
      "name": "成果管理",
      "sub_button": [
        {
          "type": "miniprogram",
          "name": "录入成果",
          "url": "https://your-domain.com/h5/output-form",
          "appid": "wx1234567890abcdef",
          "pagepath": "pages/output-form/index"
        },
        {
          "type": "miniprogram",
          "name": "成果列表",
          "url": "https://your-domain.com/h5/outputs",
          "appid": "wx1234567890abcdef",
          "pagepath": "pages/outputs/index"
        },
        {
          "type": "view",
          "name": "导出报告",
          "url": "https://your-domain.com/api/exports/excel?token=xxx"
        }
      ]
    },
    {
      "name": "我的",
      "sub_button": [
        {
          "type": "miniprogram",
          "name": "个人中心",
          "url": "https://your-domain.com/h5/profile",
          "appid": "wx1234567890abcdef",
          "pagepath": "pages/profile/index"
        },
        {
          "type": "miniprogram",
          "name": "审核工作台",
          "url": "https://your-domain.com/h5/review",
          "appid": "wx1234567890abcdef",
          "pagepath": "pages/review/index"
        }
      ]
    }
  ]
}
```

#### 使用微信 API 配置菜单
```python
import requests

def set_official_account_menu(access_token: str, menu_config: dict) -> bool:
    """
    设置公众号自定义菜单
    :param access_token: 公众号 access_token
    :param menu_config: 菜单配置（上述 JSON 格式）
    """
    url = "https://api.weixin.qq.com/cgi-bin/menu/create"
    params = {"access_token": access_token}
    resp = requests.post(url, params=params, json=menu_config)
    result = resp.json()
    return result.get("errcode") == 0
```

### 12.4 公众号推文嵌入小程序卡片

#### 使用场景
- 发布课题组动态时引导成员录入成果
- 审核提醒推文中嵌入"审核工作台"入口
- 月度报告推文中嵌入"统计仪表盘"

#### 操作步骤
1. 编辑图文消息时，点击"小程序"按钮
2. 选择已关联的小程序
3. 配置跳转路径（如 `pages/output-form/index`）
4. 自定义卡片标题和封面图
5. 发布推文

#### 动态参数传递
小程序路径支持 query 参数：
```
pages/output-detail/index?id=LW20260715001
```

小程序页面可通过 `onLoad(options)` 获取参数：
```javascript
Page({
  onLoad(options) {
    const outputId = options.id;
    this.loadOutputDetail(outputId);
  }
});
```

### 12.5 技术实现要点

#### 公众号网页授权获取 OpenID/UnionID
```python
import requests
from urllib.parse import quote

def get_official_account_oauth_url(appid: str, redirect_uri: str, scope: str = "snsapi_base") -> str:
    """
    生成公众号网页授权 URL
    :param appid: 公众号 AppID
    :param redirect_uri: 授权回调地址
    :param scope: snsapi_base（静默授权）或 snsapi_userinfo（获取用户信息）
    """
    redirect_uri_encoded = quote(redirect_uri)
    return (
        f"https://open.weixin.qq.com/connect/oauth2/authorize"
        f"?appid={appid}"
        f"&redirect_uri={redirect_uri_encoded}"
        f"&response_type=code"
        f"&scope={scope}"
        f"&state=STATE#wechat_redirect"
    )

def get_official_account_access_token(appid: str, secret: str, code: str) -> dict:
    """
    通过 code 换取 access_token 和 openid/unionid
    """
    url = "https://api.weixin.qq.com/sns/oauth2/access_token"
    params = {
        "appid": appid,
        "secret": secret,
        "code": code,
        "grant_type": "authorization_code"
    }
    resp = requests.get(url, params=params)
    return resp.json()
    # 返回：{"access_token": "...", "openid": "...", "unionid": "..."}
```

#### 小程序获取 UnionID
小程序需要满足以下条件之一才能获取 UnionID：
1. 绑定到开放平台账号
2. 用户关注了同主体的公众号

```javascript
// 小程序端
wx.login({
  success(res) {
    if (res.code) {
      // 发送 code 到后端
      wx.request({
        url: 'https://your-api.com/api/wechat/miniprogram/login',
        method: 'POST',
        data: { code: res.code },
        success(apiRes) {
          const { session_token, unionid } = apiRes.data;
          // 存储 session_token 用于后续请求
          wx.setStorageSync('session_token', session_token);
        }
      });
    }
  }
});
```

```python
# 后端处理
import requests

def miniprogram_code_to_session(appid: str, secret: str, code: str) -> dict:
    """
    小程序 code 换取 session_key 和 openid/unionid
    """
    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": appid,
        "secret": secret,
        "js_code": code,
        "grant_type": "authorization_code"
    }
    resp = requests.get(url, params=params)
    return resp.json()
    # 返回：{"openid": "...", "session_key": "...", "unionid": "..."}
```

### 12.6 方案对比与推荐

| 对接方式 | 开发成本 | 用户体验 | 适用场景 | 推荐度 |
|---------|---------|---------|---------|--------|
| **公众号菜单跳转小程序** | 低（仅配置） | 优秀 | 日常快捷入口 | ⭐⭐⭐⭐⭐ |
| **推文嵌入小程序卡片** | 低 | 优秀 | 内容营销、通知推送 | ⭐⭐⭐⭐ |
| **URL Scheme 动态链接** | 中（需后端生成） | 良好 | 短信/邮件/外部唤起 | ⭐⭐⭐ |
| **公众号 H5 页面** | 高（需开发响应式页面） | 一般 | 备用方案 | ⭐⭐ |

**综合推荐方案**：
1. **主入口**：公众号菜单配置小程序跳转（一级菜单"进入小程序"，二级菜单按功能分类）
2. **营销推广**：推文中嵌入小程序卡片（审核提醒、月度报告、新功能介绍）
3. **UnionID 统一身份**：后端以 UnionID 为主键，打通公众号和小程序用户体系
4. **备用降级**：菜单配置 `url` 字段，不支持小程序时跳转 H5 页面

---

## 七、微信小程序前端

### 12.1 小程序目录结构
```
miniprogram/
├── pages/
│   ├── login/              # 登录页
│   ├── lab-select/         # 课题组选择页
│   ├── dashboard/          # 仪表盘
│   ├── outputs/            # 成果列表
│   ├── output-detail/      # 成果详情
│   ├── output-form/        # 成果表单
│   ├── review/             # 审核工作台
│   ├── members/            # 成员管理
│   └── profile/            # 个人中心
├── components/             # 公共组件
├── utils/
│   ├── api.js              # API 封装
│   ├── auth.js             # 认证逻辑
│   └── request.js          # 网络请求
├── app.js
├── app.json
└── app.wxss
```

### 12.2 核心页面设计

#### 登录流程
```
1. 首次进入：显示"微信登录"按钮
2. 点击后调用 wx.login() + 后端 /api/wechat/login
3. 如果未绑定课题组：
   - 跳转到课题组选择页
   - 选项1：输入邀请码加入现有课题组
   - 选项2：创建新课题组（成为管理员）
4. 绑定成功后进入仪表盘
```

#### 仪表盘
- 显示课题组名称和当前角色
- 统计卡片：总成果数、待审核数、已通过数等
- 快捷入口：录入成果、查看列表、审核工作台（管理员）

#### 成果列表
- 支持搜索、筛选（类型、状态）
- 分页加载
- 长按或滑动操作：编辑、删除

#### 成果表单
- 动态表单：根据成果类型显示对应字段
- 支持选择负责人/参与人（从成员列表）
- 支持手动输入（外部合作者）
- 草稿保存功能

### 12.3 小程序技术选型

#### 原生小程序 vs 框架
- **原生小程序**：学习成本低，直接开发
- **Taro/uni-app**：可跨端（支付宝、H5），但增加复杂度

**推荐**：先用原生小程序快速验证，后续有跨端需求再迁移。

#### UI 组件库
- **WeUI**：微信官方，风格统一
- **Vant Weapp**：功能丰富，文档完善

**推荐**：Vant Weapp，表单、列表、弹窗等组件齐全。

---

## 八、安全与合规

### 12.1 数据安全

#### HTTPS 强制
- 小程序只能访问 HTTPS 接口
- 服务器必须配置合法 SSL 证书

#### 敏感数据保护
- 密码哈希：保持现有 PBKDF2 方案
- 微信 openid：不直接暴露给前端，只存储在服务端
- session_token：随机生成，定期过期

### 12.2 微信合规要求

#### 隐私协议
- 小程序首次启动需显示隐私协议
- 说明收集的信息：微信昵称、openid、课题组数据

#### 数据存储声明
- 明确数据存储位置（本地服务器 or 云端）
- 用户有权申请注销账号和删除数据

### 12.3 接口安全

#### 防刷与限流
```python
# 示例：简单的请求频率限制
from collections import defaultdict
from time import time

class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests: Dict[str, List[float]] = defaultdict(list)
    
    def allow(self, identifier: str) -> bool:
        now = time()
        self.requests[identifier] = [
            t for t in self.requests[identifier]
            if now - t < self.window
        ]
        if len(self.requests[identifier]) < self.max_requests:
            self.requests[identifier].append(now)
            return True
        return False
```

#### CSRF 防护（小程序场景）
- 小程序调用 API 时携带 `session_token`
- 服务端验证 token 有效性
- 避免使用 Cookie（小程序不支持）

---

## 九、部署与运维

### 12.1 部署架构

#### 开发/测试阶段
```
本地服务器 + 内网穿透（natapp/frp）
└─> 提供 HTTPS 端点供小程序测试
```

#### 生产阶段
```
云服务器（阿里云/腾讯云）
├─> Nginx 反向代理
├─> Python 应用（Gunicorn/uWSGI）
└─> 数据备份（定时任务）
```

### 12.2 微信小程序注册

#### 注册流程
1. 前往 [微信公众平台](https://mp.weixin.qq.com/) 注册小程序账号
2. 完成认证（企业/组织需认证，个人小程序有功能限制）
3. 获取 AppID 和 AppSecret
4. 配置服务器域名白名单

#### 小程序审核要点
- 功能描述清晰：科研成果管理
- 提供测试账号和使用说明
- 确保无违规内容（广告、支付等）

### 12.3 监控与日志

#### 日志记录
- API 请求日志：记录请求路径、参数、响应时间
- 错误日志：捕获异常并记录堆栈
- 审计日志：保持现有 `audit_logs.json` 机制

#### 性能监控
- 接口响应时间
- 数据库查询耗时（若升级到数据库）
- 小程序端崩溃率（微信后台自带）

---

## 十、开发计划与里程碑

### 12.1 阶段划分

#### P0（核心功能，2-3 周）
1. **后端 API 开发**
   - 扩展 `web.py`，新增 `/api/*` 路由
   - 实现微信登录接口 `/api/wechat/login`
   - 实现课题组管理接口（注册、绑定、切换）
   - 实现成果 CRUD API
   - 多课题组数据隔离

2. **小程序前端开发**
   - 登录页 + 课题组选择页
   - 仪表盘
   - 成果列表 + 成果详情
   - 成果表单（新增/编辑）

3. **测试与联调**
   - 单元测试：新增 API 端点
   - 集成测试：小程序 + 后端联调
   - 用户测试：邀请课题组成员试用

#### P1（增强功能，1-2 周）
- 审核工作台（管理员）
- 成员管理
- 项目管理
- 外部数据抓取（DOI/PubMed/专利）
- Excel 导出

#### P2（长期优化）
- 独立 API 服务（Flask/FastAPI）
- 数据库迁移（SQLite → PostgreSQL）
- 云端部署与负载均衡
- 消息推送（审核通知）
- 数据统计图表（ECharts）

### 12.2 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 微信小程序审核不通过 | 无法上线 | 提前准备完整的功能说明和测试账号；确保合规 |
| 现有架构性能瓶颈 | 多课题组并发时响应慢 | 先用文件锁保证数据一致性；后续升级数据库 |
| 数据迁移失败 | 现有数据丢失 | 编写完善的迁移脚本并充分测试；保留备份 |
| HTTPS 证书配置问题 | 小程序无法访问 | 使用 Let's Encrypt 免费证书；提前测试 |

---

## 十一、关键决策点

### 12.1 数据存储选择

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **继续使用 JSON 文件** | 改动最小；无额外依赖；易于备份 | 并发性能差；查询效率低 | ⭐⭐⭐⭐ (短期) |
| **升级到 SQLite** | 支持 SQL 查询；单文件易部署 | 并发写入有限制 | ⭐⭐⭐ (中期) |
| **升级到 PostgreSQL** | 高性能；成熟方案；支持大规模并发 | 部署复杂度增加 | ⭐⭐ (长期) |

**决策**：阶段一继续使用 JSON 文件 + 文件锁，待用户规模增长后再升级。

### 12.2 后端架构选择

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **扩展现有 `web.py`** | 改动最小；快速上线 | 代码耦合度高；难以扩展 | ⭐⭐⭐⭐ (短期) |
| **独立 Flask API** | 架构清晰；易于测试 | 需要重构部分逻辑 | ⭐⭐⭐ (中期) |
| **FastAPI + 异步** | 高性能；现代化 | 学习成本高；生态较新 | ⭐⭐ (长期) |

**决策**：阶段一扩展 `web.py`，保持最小改动原则。

### 12.3 小程序技术选型

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **原生小程序** | 学习成本低；性能最优 | 不可跨端 | ⭐⭐⭐⭐ (推荐) |
| **Taro** | 可编译到多端；React 开发体验 | 增加构建复杂度 | ⭐⭐⭐ (有跨端需求时) |
| **uni-app** | 可编译到多端；Vue 开发体验 | 社区相对分散 | ⭐⭐ |

**决策**：使用原生小程序，配合 Vant Weapp 组件库。

---

## 十二、后续扩展方向

### 12.1 功能扩展
- 消息推送：审核通知、成果变更提醒
- 协作功能：成果多人编辑、评论功能
- 数据可视化：成果统计图表、年度报告
- 移动端优化：支持支付宝小程序、H5 页面

### 12.2 技术升级
- 数据库迁移：JSON → SQLite → PostgreSQL
- 架构演进：单体 → 微服务
- 容器化部署：Docker + Kubernetes
- CI/CD 流水线：自动化测试、部署

### 12.3 生态对接
- 与学校/机构系统对接：统一身份认证（LDAP/CAS）
- 与外部数据库对接：自动同步 CNKI、万方等
- 开放 API：供第三方系统调用

---

## 十三、总结

本技术方案大纲遵循"最小改动、快速验证、渐进演进"的原则，分阶段实现微信小程序接入和多课题组支持：

**核心策略**：
1. **数据隔离**：通过 `lab_id` 和多级目录结构实现课题组数据隔离
2. **认证增强**：集成微信登录，保持现有密码登录兼容
3. **API 扩展**：在 `web.py` 基础上新增 RESTful API 端点
4. **前端重建**：使用原生小程序 + Vant Weapp 快速构建移动端

**交付物**：
- 多课题组数据模型与存储结构
- 完整的后端 API 接口
- 功能完备的微信小程序
- 数据迁移脚本与部署文档

**验收标准**：
- 多个课题组可独立注册和登录
- 课题组之间数据完全隔离
- 小程序可完成成果录入、审核等核心流程
- 现有 Web UI 功能不受影响

---

**制定者**：AI Assistant (Kiro)  
**审核者**：待用户确认  
**版本**：v1.0 (初稿)
