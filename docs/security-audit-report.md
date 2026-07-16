# 微信小程序 API 安全审查报告

**审查日期**: 2026-07-16  
**审查范围**: 微信小程序登录、会话管理、权限控制、多课题组隔离  
**审查人**: security-specialist agent

---

## 执行摘要

本次审查发现 **3 个 P0 高危问题**、**11 个 P1 中危问题**、**7 个 P2 低危问题**。主要风险集中在：

1. **敏感数据泄露**：`session_key` 被返回给客户端
2. **访问控制失效**：缺少速率限制，可被暴力攻击
3. **会话管理缺陷**：内存存储、无清理机制、缺少 CSRF 保护
4. **输入验证不足**：多个参数缺少长度和格式验证

---

## P0 高危问题

### P0-1: session_key 泄露 (CWE-200: Sensitive Data Exposure)

**位置**: `/src/lab_literature_manager/api_extensions.py:351`

**问题描述**:
```python
return {
    "status": "need_bind",
    "unionid": wechat_session.unionid,
    "openid": wechat_session.openid,
    "session_key": wechat_session.session_key,  # ← 敏感信息泄露
}
```

微信的 `session_key` 用于解密用户敏感数据（手机号、运动数据等）。将其返回给客户端后，任何截获响应的攻击者（如中间人、XSS）都可以解密用户数据。

**攻击场景**:
1. 用户在公共 WiFi 下使用小程序
2. 中间人截获登录响应，获取 `session_key`
3. 攻击者使用 `session_key` 解密用户手机号、地理位置等敏感信息

**修复方案**:
```python
# api_extensions.py:346-352
if user:
    # 用户已存在，创建会话
    session_token, csrf_token = self._create_session(user.username, user.lab_id)
    return {
        "status": "success",
        "session_token": session_token,
        "csrf_token": csrf_token,
        "username": user.username,
        "display_name": user.display_name,
        "lab_id": user.lab_id,
        "role": user.role.value,
    }
else:
    # 用户不存在，需要绑定课题组
    # ✅ 服务端存储 session_key，返回临时 token
    temp_token = secrets.token_urlsafe(32)
    self._pending_binds[temp_token] = {
        "openid": wechat_session.openid,
        "unionid": wechat_session.unionid,
        "session_key": wechat_session.session_key,  # 仅存储在服务端
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    return {
        "status": "need_bind",
        "bind_token": temp_token,  # 返回临时 token
        "openid": wechat_session.openid,
        "unionid": wechat_session.unionid,
        # session_key 不返回
    }
```

**验证步骤**:
```bash
# 1. 发送登录请求
curl -X POST http://localhost:8080/api/v1/wechat/miniprogram/login \
  -H "Content-Type: application/json" \
  -d '{"code": "test_code"}'

# 2. 检查响应中是否包含 session_key
# ❌ 修复前：响应包含 "session_key": "xxxxx"
# ✅ 修复后：响应只包含 "bind_token": "xxxxx"
```

---

### P0-2: 缺少速率限制 (CWE-307: Brute Force)

**位置**: `/src/lab_literature_manager/api_extensions.py:281` (所有 API 端点)

**问题描述**:
登录接口没有速率限制，攻击者可以：
- 暴力破解邀请码（6 字节 base64，约 2^48 种可能）
- 枚举有效的 OpenID
- 消耗服务器资源（调用微信 API 有配额限制）

**攻击场景**:
```python
# 攻击脚本示例
for code in generate_codes():
    response = requests.post(
        "http://target/api/v1/wechat/miniprogram/login",
        json={"code": code}
    )
    if "session_token" in response.json():
        print(f"Valid code found: {code}")
```

**修复方案**:
```python
# 新增速率限制装饰器
from collections import defaultdict
from datetime import datetime, timedelta, timezone

class RateLimiter:
    """简单的速率限制器（生产环境应使用 Redis）"""
    
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[datetime]] = defaultdict(list)
    
    def check(self, key: str) -> bool:
        """检查是否超过速率限制"""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.window_seconds)
        
        # 清理过期记录
        self._requests[key] = [
            t for t in self._requests[key] if t > cutoff
        ]
        
        # 检查限制
        if len(self._requests[key]) >= self.max_requests:
            return False
        
        self._requests[key].append(now)
        return True

# 在 APIRequestHandler.__init__ 中初始化
self._login_limiter = RateLimiter(max_requests=10, window_seconds=60)  # 每分钟 10 次

# 在 api_wechat_miniprogram_login 中使用
def api_wechat_miniprogram_login(self, body: Dict[str, Any], client_ip: str) -> Dict[str, Any]:
    # 速率限制检查
    if not self._login_limiter.check(client_ip):
        return {"error": "Too many requests, please try again later"}
    
    code = body.get("code", "")
    # ... 其余代码
```

**验证步骤**:
```bash
# 发送 15 次快速请求
for i in {1..15}; do
  curl -X POST http://localhost:8080/api/v1/wechat/miniprogram/login \
    -H "Content-Type: application/json" \
    -d '{"code": "test"}' &
done
wait

# ✅ 前 10 次返回正常响应
# ✅ 后 5 次返回 429 Too Many Requests 或 {"error": "Too many requests"}
```

---

### P0-3: CSRF 保护不足 (CWE-352: CSRF)

**位置**: API 端点未验证 CSRF token

**问题描述**:
虽然 `_create_session()` 生成了 `csrf_token`，但 API 端点（如 `api_wechat_bind_lab`、`api_lab_regenerate_invite_code`）没有验证 CSRF token。攻击者可以通过恶意网站触发用户执行非预期操作。

**攻击场景**:
```html
<!-- 攻击者网站 evil.com -->
<script>
fetch('https://target.com/api/v1/wechat/bind', {
  method: 'POST',
  credentials: 'include',  // 携带 session cookie
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    openid: 'victim_openid',
    invite_code: 'attacker_code',  // 将受害者加入攻击者的课题组
    display_name: 'Victim'
  })
});
</script>
```

**修复方案**:
```python
def _verify_csrf_token(self, body: Dict[str, Any], session_token: str) -> bool:
    """验证 CSRF token"""
    csrf_token = body.get("csrf_token", "")
    if not csrf_token:
        return False
    
    session = self._get_session(session_token)
    if not session:
        return False
    
    return hmac.compare_digest(csrf_token, session.csrf_token)

def api_wechat_bind_lab(self, body: Dict[str, Any], session_token: str = "") -> Dict[str, Any]:
    """绑定课题组接口（需要 CSRF 保护）"""
    
    # ✅ 验证 CSRF token（对于状态变更操作）
    if session_token and not self._verify_csrf_token(body, session_token):
        return {"error": "Invalid CSRF token"}
    
    unionid = body.get("unionid", "")
    # ... 其余代码
```

**验证步骤**:
```bash
# 1. 正常登录获取 session_token 和 csrf_token
LOGIN_RESP=$(curl -X POST http://localhost:8080/api/v1/wechat/miniprogram/login \
  -H "Content-Type: application/json" \
  -d '{"code": "valid_code"}')

SESSION_TOKEN=$(echo $LOGIN_RESP | jq -r '.session_token')
CSRF_TOKEN=$(echo $LOGIN_RESP | jq -r '.csrf_token')

# 2. 尝试不带 csrf_token 的请求
curl -X POST http://localhost:8080/api/v1/wechat/bind \
  -H "Authorization: Bearer $SESSION_TOKEN" \
  -d '{"invite_code": "test", "display_name": "Test"}'
# ❌ 应返回 {"error": "Invalid CSRF token"}

# 3. 带正确 csrf_token 的请求
curl -X POST http://localhost:8080/api/v1/wechat/bind \
  -H "Authorization: Bearer $SESSION_TOKEN" \
  -d "{\"invite_code\": \"test\", \"display_name\": \"Test\", \"csrf_token\": \"$CSRF_TOKEN\"}"
# ✅ 应成功
```

---

## P1 中危问题

### P1-1: 会话存储在内存中 (CWE-311: Session Fixation)

**位置**: `/src/lab_literature_manager/api_extensions.py:145`

**问题**:
```python
self._sessions: Dict[str, APISession] = {}
```

- 重启后所有会话丢失
- 无法跨进程共享（多实例部署时会话不同步）
- 内存泄漏风险（过期会话不清理）

**修复方案**:
使用 Redis 或数据库存储会话：
```python
# 使用 Redis 示例（需要 pip install redis）
import redis
import json

class RedisSessionStore:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url)
    
    def create_session(self, username: str, lab_id: str) -> Tuple[str, str]:
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(16)
        
        session_data = {
            "username": username,
            "lab_id": lab_id,
            "csrf_token": csrf_token,
        }
        
        # 设置 TTL 为 8 小时
        self.redis.setex(
            f"session:{session_token}",
            SESSION_TTL_HOURS * 3600,
            json.dumps(session_data)
        )
        
        return session_token, csrf_token
    
    def get_session(self, session_token: str) -> Optional[APISession]:
        data = self.redis.get(f"session:{session_token}")
        if not data:
            return None
        
        session_dict = json.loads(data)
        return APISession(
            username=session_dict["username"],
            lab_id=session_dict["lab_id"],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS),
            csrf_token=session_dict["csrf_token"],
        )
```

---

### P1-2: 输入验证不足

**位置**: 多个 API 端点

**问题列表**:

1. `code` 参数没有长度限制 (api_extensions.py:300)
```python
# 修复前
code = body.get("code", "")
if not code:
    return {"error": "Missing code parameter"}

# 修复后
code = body.get("code", "").strip()
if not code or len(code) > 128:  # 微信 code 通常 < 100 字符
    return {"error": "Invalid code parameter"}
```

2. `display_name` 没有长度限制 (api_extensions.py:382)
```python
display_name = body.get("display_name", "").strip()
if len(display_name) > 100:
    return {"error": "Display name too long (max 100 characters)"}
```

3. `lab_name` 没有长度限制 (api_extensions.py:392)
```python
lab_name = body.get("lab_name", "").strip()
if not lab_name or len(lab_name) > 200:
    return {"error": "Invalid lab name (1-200 characters)"}
```

4. `invite_code` 没有格式验证 (api_extensions.py:434)
```python
invite_code = body.get("invite_code", "").strip()
if not invite_code or not re.match(r'^[A-Za-z0-9_-]{6,20}$', invite_code):
    return {"error": "Invalid invite code format"}
```

---

### P1-3: 用户名冲突风险

**位置**: `/src/lab_literature_manager/api_extensions.py:397, 442`

**问题**:
```python
username = f"wechat_{openid[:16]}"
```

OpenID 前 16 个字符可能重复，导致用户名冲突。

**修复方案**:
```python
# 使用完整 openid 的哈希
username = f"wechat_{hashlib.sha256(openid.encode()).hexdigest()[:16]}"

# 或者检查冲突
base_username = f"wechat_{openid[:16]}"
username = base_username
counter = 1
while self._find_user_by_username(username):
    username = f"{base_username}_{counter}"
    counter += 1
```

---

### P1-4: 文件操作缺少并发控制

**位置**: `/src/lab_literature_manager/api_extensions.py:150-177`

**问题**:
```python
def _load_users(self) -> List[WebUser]:
    # ... 读取文件

def _save_users(self, users: List[WebUser]) -> None:
    # ... 写入文件
```

多个并发请求可能导致数据覆盖。

**修复方案**:
```python
import threading

class APIRequestHandler:
    def __init__(self, ...):
        # ...
        self._users_lock = threading.Lock()
    
    def _load_users(self) -> List[WebUser]:
        with self._users_lock:
            # ... 读取文件
    
    def _save_users(self, users: List[WebUser]) -> None:
        with self._users_lock:
            # ... 写入文件
```

---

### P1-5: 配置验证缺失

**位置**: `/src/lab_literature_manager/config.py:51-59`

**问题**:
没有验证配置是否为占位符值。

**修复方案**:
```python
def load_config(env_file: str = ".env") -> Config:
    # ... 加载配置
    
    config = Config(...)
    
    # ✅ 验证配置
    if "your_" in config.wechat_miniprogram_appid.lower():
        raise ValueError("Please configure WECHAT_MINIPROGRAM_APPID in .env file")
    
    if not config.wechat_miniprogram_secret or len(config.wechat_miniprogram_secret) < 16:
        raise ValueError("Invalid WECHAT_MINIPROGRAM_SECRET")
    
    return config
```

---

### P1-6: 错误信息泄露用户枚举

**位置**: `/src/lab_literature_manager/api_extensions.py:263-277`

**问题**:
```python
if not session:
    return None, "Invalid or expired session"  # 可区分 session 不存在

if not user:
    return None, "User not found"  # 可区分用户不存在

if user.account_status != ACCOUNT_STATUS_ACTIVE:
    return None, "User account is not active"  # 可区分用户状态
```

**修复方案**:
```python
# 统一错误信息
if not session or not user or user.account_status != ACCOUNT_STATUS_ACTIVE:
    return None, "Authentication failed"
```

---

### P1-7: 邀请码强度不足

**位置**: `/src/lab_literature_manager/multilab_repository.py:92`

**问题**:
```python
invite_code = secrets.token_urlsafe(6)  # 仅 6 字节 = 48 位熵
```

6 字节 base64 编码后约 8 个字符，暴力破解空间为 2^48 ≈ 281 万亿次。如果没有速率限制，可能在合理时间内破解。

**修复方案**:
```python
invite_code = secrets.token_urlsafe(12)  # 12 字节 = 96 位熵，更安全
```

---

### P1-8: 会话固定攻击

**位置**: 会话管理逻辑

**问题**:
登录成功后没有轮换 session token，可能被利用进行会话固定攻击。

**修复方案**:
```python
def api_wechat_miniprogram_login(self, body: Dict[str, Any]) -> Dict[str, Any]:
    # ... 验证 code
    
    if user:
        # ✅ 登录成功后生成新 session token（而不是复用旧 token）
        session_token, csrf_token = self._create_session(user.username, user.lab_id)
        return {
            "status": "success",
            "session_token": session_token,
            "csrf_token": csrf_token,
            # ...
        }
```

---

### P1-9: 缺少 HTTPS 强制

**位置**: `/src/lab_literature_manager/config.py:57`

**问题**:
默认监听 `0.0.0.0:8080`（HTTP），会话 cookie 和敏感数据可能被窃听。

**修复方案**:
```python
# config.py 添加 HTTPS 配置
@dataclass
class Config:
    # ...
    force_https: bool = True  # 强制 HTTPS
    ssl_cert_file: str = ""
    ssl_key_file: str = ""

# web.py 添加 HTTPS 重定向
def do_GET(self):
    if self.config.force_https and not self.is_secure_connection():
        self.send_response(301)
        https_url = f"https://{self.headers['Host']}{self.path}"
        self.send_header("Location", https_url)
        self.end_headers()
        return
    # ...
```

---

### P1-10: 缺少 Content-Type 验证

**位置**: API 端点处理

**问题**:
没有验证 `Content-Type: application/json`，可能被利用进行 CSRF 或解析混淆攻击。

**修复方案**:
```python
def handle_api_request(self, handler: BaseHTTPRequestHandler):
    content_type = handler.headers.get("Content-Type", "")
    if not content_type.startswith("application/json"):
        self.send_json_response(handler, 400, {"error": "Content-Type must be application/json"})
        return
    # ...
```

---

### P1-11: 缺少请求大小限制

**位置**: API 端点处理

**问题**:
没有限制请求体大小，可能被用于 DoS 攻击。

**修复方案**:
```python
def parse_json_body(self, handler: BaseHTTPRequestHandler, max_size: int = 1024 * 1024) -> Optional[Dict]:
    """解析 JSON 请求体（带大小限制）"""
    content_length = int(handler.headers.get("Content-Length", 0))
    
    if content_length > max_size:
        self.send_json_response(handler, 413, {"error": "Request too large"})
        return None
    
    body_bytes = handler.rfile.read(content_length)
    try:
        return json.loads(body_bytes)
    except json.JSONDecodeError:
        self.send_json_response(handler, 400, {"error": "Invalid JSON"})
        return None
```

---

## P2 低危问题

### P2-1: 错误信息泄露内部细节

**位置**: `/src/lab_literature_manager/wechat_api.py:65, 125`

**问题**:
```python
raise WeChatAPIError(-1, f"Network error: {str(e)}")
```

可能泄露内部网络拓扑或配置信息。

**修复方案**:
```python
# 日志记录详细错误
import logging
logger.error(f"WeChat API network error: {str(e)}")

# 返回通用错误
raise WeChatAPIError(-1, "Network error occurred")
```

---

### P2-2: 缺少日志审计

**位置**: 所有 API 端点

**问题**:
没有记录关键操作日志（登录、绑定课题组、权限变更）。

**修复方案**:
```python
import logging

logger = logging.getLogger(__name__)

def api_wechat_miniprogram_login(self, body: Dict[str, Any], client_ip: str) -> Dict[str, Any]:
    code = body.get("code", "")
    
    try:
        # ... 登录逻辑
        logger.info(f"Login successful: user={user.username}, ip={client_ip}")
        return {"status": "success", ...}
    except Exception as e:
        logger.warning(f"Login failed: code={code[:8]}..., ip={client_ip}, error={str(e)}")
        return {"error": "Login failed"}
```

---

### P2-3: 缺少账号锁定机制

**位置**: 登录逻辑

**问题**:
多次登录失败后没有锁定账号。

**修复方案**:
```python
class AccountLockManager:
    def __init__(self, max_attempts: int = 5, lock_duration: int = 900):
        self.max_attempts = max_attempts
        self.lock_duration = lock_duration  # 15 分钟
        self._failed_attempts: Dict[str, List[datetime]] = defaultdict(list)
        self._locked_accounts: Dict[str, datetime] = {}
    
    def is_locked(self, identifier: str) -> bool:
        if identifier in self._locked_accounts:
            if datetime.now(timezone.utc) < self._locked_accounts[identifier]:
                return True
            else:
                del self._locked_accounts[identifier]
        return False
    
    def record_failure(self, identifier: str) -> None:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.lock_duration)
        
        # 清理过期记录
        self._failed_attempts[identifier] = [
            t for t in self._failed_attempts[identifier] if t > cutoff
        ]
        
        self._failed_attempts[identifier].append(now)
        
        # 检查是否需要锁定
        if len(self._failed_attempts[identifier]) >= self.max_attempts:
            self._locked_accounts[identifier] = now + timedelta(seconds=self.lock_duration)
```

---

### P2-4: 缺少会话数量限制

**位置**: 会话管理

**问题**:
单个用户可以创建无限个会话。

**修复方案**:
```python
def _create_session(self, username: str, lab_id: str) -> Tuple[str, str]:
    # ✅ 限制单个用户的并发会话数
    user_sessions = [
        token for token, sess in self._sessions.items()
        if sess.username == username
    ]
    
    if len(user_sessions) >= 5:  # 最多 5 个并发会话
        # 删除最旧的会话
        oldest_token = min(user_sessions, key=lambda t: self._sessions[t].expires_at)
        del self._sessions[oldest_token]
    
    # ... 创建新会话
```

---

### P2-5: 缺少 SameSite Cookie 属性

**位置**: `/src/lab_literature_manager/web.py:1419`

**问题**:
虽然设置了 `samesite="Lax"`，但 API 可能通过 `Authorization` header 传递 token，此时 Cookie 属性无效。

**修复方案**:
```python
# 统一使用 Authorization header，不依赖 Cookie
# 前端示例：
# fetch('/api/v1/labs', {
#   headers: {
#     'Authorization': `Bearer ${sessionToken}`,
#     'X-CSRF-Token': csrfToken
#   }
# })
```

---

### P2-6: 缺少会话续期策略

**位置**: `/src/lab_literature_manager/api_extensions.py:240`

**问题**:
API 的 `_get_session()` 不续期，8 小时后强制过期（即使用户活跃）。

**修复方案**:
```python
def _get_session(self, session_token: str) -> Optional[APISession]:
    session = self._sessions.get(session_token)
    if not session:
        return None
    
    # 检查是否过期
    if datetime.now(timezone.utc) > session.expires_at:
        del self._sessions[session_token]
        return None
    
    # ✅ 续期（滑动过期）
    session.expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
    
    return session
```

---

### P2-7: 缺少 X-Frame-Options 和 CSP 头

**位置**: HTTP 响应头

**问题**:
缺少安全响应头，可能被用于点击劫持或 XSS 攻击。

**修复方案**:
```python
def send_security_headers(self, handler: BaseHTTPRequestHandler):
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-XSS-Protection", "1; mode=block")
    handler.send_header("Content-Security-Policy", 
                       "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'")
    handler.send_header("Strict-Transport-Security", 
                       "max-age=31536000; includeSubDomains")
```

---

## 修复优先级建议

### 立即修复 (P0)
1. **P0-1**: 移除 `session_key` 返回
2. **P0-2**: 实现速率限制
3. **P0-3**: 添加 CSRF 验证

### 近期修复 (P1)
1. **P1-1**: 迁移到 Redis 或数据库会话存储
2. **P1-2**: 添加输入验证
3. **P1-4**: 添加文件并发锁
4. **P1-5**: 验证配置完整性
5. **P1-9**: 强制 HTTPS

### 后续优化 (P2)
1. **P2-2**: 添加审计日志
2. **P2-3**: 实现账号锁定
3. **P2-7**: 添加安全响应头

---

## 安全测试用例

见下一个文件：`tests/test_security.py`

---

## 参考资料

- [OWASP Top 10 2021](https://owasp.org/Top10/)
- [微信小程序登录安全指南](https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/login.html)
- [CWE Top 25](https://cwe.mitre.org/top25/)
