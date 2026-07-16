"""
安全修复补丁

包含所有 P0 和部分 P1 问题的修复代码。
应用方式：
1. 审查修复代码
2. 逐个应用到对应文件
3. 运行安全测试验证
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


# ==================== 速率限制器 ====================

class RateLimiter:
    """
    简单的内存速率限制器。

    生产环境建议使用 Redis 实现分布式速率限制。
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[datetime]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """
        检查是否超过速率限制。

        :param key: 限流键（如 IP 地址）
        :return: True 允许请求，False 拒绝请求
        """
        with self._lock:
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

    def reset(self, key: str) -> None:
        """重置指定键的限流记录"""
        with self._lock:
            self._requests.pop(key, None)


# ==================== 账号锁定管理器 ====================

class AccountLockManager:
    """
    账号锁定管理器，防止暴力破解。
    """

    def __init__(self, max_attempts: int = 5, lock_duration_seconds: int = 900):
        self.max_attempts = max_attempts
        self.lock_duration = lock_duration_seconds
        self._failed_attempts: Dict[str, List[datetime]] = defaultdict(list)
        self._locked_accounts: Dict[str, datetime] = {}
        self._lock = threading.Lock()

    def is_locked(self, identifier: str) -> bool:
        """检查账号是否被锁定"""
        with self._lock:
            if identifier in self._locked_accounts:
                if datetime.now(timezone.utc) < self._locked_accounts[identifier]:
                    return True
                else:
                    del self._locked_accounts[identifier]
            return False

    def record_failure(self, identifier: str) -> None:
        """记录登录失败"""
        with self._lock:
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

    def reset(self, identifier: str) -> None:
        """重置失败记录（登录成功后调用）"""
        with self._lock:
            self._failed_attempts.pop(identifier, None)
            self._locked_accounts.pop(identifier, None)


# ==================== 待绑定会话管理 ====================

@dataclass
class PendingBindSession:
    """待绑定的微信登录会话"""
    openid: str
    unionid: str
    session_key: str  # 仅存储在服务端，不返回给客户端
    expires_at: datetime


class PendingBindStore:
    """待绑定会话存储"""

    def __init__(self):
        self._pending: Dict[str, PendingBindSession] = {}
        self._lock = threading.Lock()

    def create(self, openid: str, unionid: str, session_key: str) -> str:
        """
        创建待绑定会话。

        :return: bind_token
        """
        with self._lock:
            bind_token = secrets.token_urlsafe(32)
            self._pending[bind_token] = PendingBindSession(
                openid=openid,
                unionid=unionid,
                session_key=session_key,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
            )
            return bind_token

    def get(self, bind_token: str) -> Optional[PendingBindSession]:
        """获取待绑定会话"""
        with self._lock:
            session = self._pending.get(bind_token)
            if not session:
                return None

            # 检查过期
            if datetime.now(timezone.utc) > session.expires_at:
                del self._pending[bind_token]
                return None

            return session

    def consume(self, bind_token: str) -> Optional[PendingBindSession]:
        """消费待绑定会话（一次性使用）"""
        with self._lock:
            session = self.get(bind_token)
            if session:
                del self._pending[bind_token]
            return session


# ==================== 输入验证器 ====================

class InputValidator:
    """输入验证工具"""

    @staticmethod
    def validate_code(code: str) -> Optional[str]:
        """
        验证微信 code 参数。

        :return: 错误信息，None 表示验证通过
        """
        if not code or not isinstance(code, str):
            return "Invalid code parameter"

        code = code.strip()
        if not code or len(code) > 128:
            return "Invalid code parameter"

        return None

    @staticmethod
    def validate_display_name(name: str) -> Optional[str]:
        """验证显示名称"""
        if not name or not isinstance(name, str):
            return "Display name is required"

        name = name.strip()
        if not name or len(name) > 100:
            return "Display name too long (max 100 characters)"

        return None

    @staticmethod
    def validate_lab_name(name: str) -> Optional[str]:
        """验证课题组名称"""
        if not name or not isinstance(name, str):
            return "Lab name is required"

        name = name.strip()
        if not name or len(name) > 200:
            return "Invalid lab name (1-200 characters)"

        return None

    @staticmethod
    def validate_invite_code(code: str) -> Optional[str]:
        """验证邀请码格式"""
        if not code or not isinstance(code, str):
            return "Invite code is required"

        code = code.strip()
        # 邀请码应该是 base64url 字符，6-20 个字符
        if not re.match(r'^[A-Za-z0-9_-]{6,20}$', code):
            return "Invalid invite code format"

        return None


# ==================== API 请求处理器修复版 ====================

class SecureAPIRequestHandler:
    """
    安全增强版 API 请求处理器。

    应用到 api_extensions.py 的 APIRequestHandler 类。
    """

    def __init__(self, multilab_repo, wechat_config, users_file: str):
        # ... 原有初始化代码

        # ✅ 新增：速率限制器
        self._login_limiter = RateLimiter(max_requests=10, window_seconds=60)
        self._api_limiter = RateLimiter(max_requests=100, window_seconds=60)

        # ✅ 新增：账号锁定管理
        self._account_locker = AccountLockManager(max_attempts=5, lock_duration_seconds=900)

        # ✅ 新增：待绑定会话存储
        self._pending_binds = PendingBindStore()

        # ✅ 新增：文件操作锁
        self._users_lock = threading.Lock()

    # ==================== 修复后的登录接口 ====================

    def api_wechat_miniprogram_login(
        self,
        body: Dict[str, Any],
        client_ip: str
    ) -> Dict[str, Any]:
        """
        POST /api/v1/wechat/miniprogram/login
        小程序登录接口（安全增强版）。
        """
        # ✅ P0-2: 速率限制
        if not self._login_limiter.check(client_ip):
            return {"error": "Too many requests, please try again later"}

        # ✅ P1-2: 输入验证
        code = body.get("code", "")
        error = InputValidator.validate_code(code)
        if error:
            return {"error": error}

        code = code.strip()

        try:
            # 调用微信 API 换取 openid/unionid
            from .wechat_api import miniprogram_code_to_session
            wechat_session = miniprogram_code_to_session(
                self.wechat_config.miniprogram_appid,
                self.wechat_config.miniprogram_secret,
                code,
            )
        except Exception as e:
            # ✅ P2-1: 不泄露内部错误细节
            import logging
            logging.error(f"WeChat API error: {str(e)}")
            return {"error": "Login failed, please try again"}

        # 优先使用 unionid，没有则使用 openid
        identifier = wechat_session.unionid or wechat_session.openid
        if not identifier:
            return {"error": "Login failed"}

        # ✅ P2-3: 检查账号锁定
        if self._account_locker.is_locked(identifier):
            return {"error": "Account temporarily locked due to multiple failed attempts"}

        # 查找用户
        user = None
        if wechat_session.unionid:
            user = self._find_user_by_unionid(wechat_session.unionid)

        if not user and wechat_session.openid:
            # 尝试通过小程序 openid 查找
            with self._users_lock:
                if self._users_cache is None:
                    self._users_cache = self._load_users()
                for u in self._users_cache:
                    if u.wechat_miniprogram_openid == wechat_session.openid:
                        user = u
                        break

        if user:
            # 用户已存在，创建会话
            # ✅ P2-3: 登录成功，重置失败计数
            self._account_locker.reset(identifier)

            # ✅ P1-8: 生成新 session token（防止会话固定）
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
            # ✅ P0-1: session_key 只存储在服务端，不返回给客户端
            bind_token = self._pending_binds.create(
                openid=wechat_session.openid,
                unionid=wechat_session.unionid,
                session_key=wechat_session.session_key  # 仅存储在服务端
            )

            return {
                "status": "need_bind",
                "bind_token": bind_token,  # 返回临时 token
                "openid": wechat_session.openid,
                "unionid": wechat_session.unionid,
                # ✅ session_key 不返回
            }

    # ==================== 修复后的绑定接口 ====================

    def api_wechat_bind_lab(
        self,
        body: Dict[str, Any],
        client_ip: str,
        session_token: str = ""
    ) -> Dict[str, Any]:
        """
        POST /api/v1/wechat/bind
        绑定课题组接口（安全增强版）。
        """
        # ✅ P0-2: 速率限制
        if not self._api_limiter.check(client_ip):
            return {"error": "Too many requests"}

        # ✅ P0-3: CSRF 保护（对于已登录用户的操作）
        if session_token and not self._verify_csrf_token(body, session_token):
            return {"error": "Invalid CSRF token"}

        # ✅ P1-2: 输入验证
        bind_token = body.get("bind_token", "")
        if not bind_token:
            return {"error": "Missing bind_token parameter"}

        # 获取待绑定会话
        pending_session = self._pending_binds.consume(bind_token)
        if not pending_session:
            return {"error": "Invalid or expired bind token"}

        openid = pending_session.openid
        unionid = pending_session.unionid

        # 验证 display_name
        display_name = body.get("display_name", "").strip()
        error = InputValidator.validate_display_name(display_name)
        if error:
            return {"error": error}

        if not display_name:
            display_name = f"用户_{openid[:8]}"

        # 检查是否创建新课题组
        if body.get("create_lab"):
            lab_name = body.get("lab_name", "").strip()
            error = InputValidator.validate_lab_name(lab_name)
            if error:
                return {"error": error}

            lab_subtitle = body.get("lab_subtitle", "").strip()

            # ✅ P1-3: 使用哈希避免用户名冲突
            username = f"wechat_{hashlib.sha256(openid.encode()).hexdigest()[:16]}"

            # 创建新课题组
            lab = self.multilab_repo.create_lab(
                lab_name=lab_name,
                lab_subtitle=lab_subtitle,
                admin_username=username,
            )

            # 创建管理员用户
            from .models import Role
            user = self._create_user_object(
                username=username,
                display_name=display_name,
                role=Role.ADMIN,
                lab_id=lab.lab_id,
                wechat_unionid=unionid,
                wechat_miniprogram_openid=openid,
            )

            with self._users_lock:
                self._create_user(user)

            # 创建会话
            session_token, csrf_token = self._create_session(username, lab.lab_id)

            return {
                "status": "success",
                "session_token": session_token,
                "csrf_token": csrf_token,
                "lab_id": lab.lab_id,
                "lab_name": lab.lab_name,
                "invite_code": lab.invite_code,
            }

        # 加入现有课题组
        invite_code = body.get("invite_code", "").strip()
        error = InputValidator.validate_invite_code(invite_code)
        if error:
            return {"error": error}

        lab = self.multilab_repo.find_lab_by_invite_code(invite_code)
        if not lab:
            # ✅ P1-6: 统一错误信息，防止枚举
            return {"error": "Invalid invite code"}

        # ✅ P1-3: 使用哈希避免用户名冲突
        username = f"wechat_{hashlib.sha256(openid.encode()).hexdigest()[:16]}"

        # 创建成员用户
        from .models import Role
        user = self._create_user_object(
            username=username,
            display_name=display_name,
            role=Role.MEMBER,
            lab_id=lab.lab_id,
            wechat_unionid=unionid,
            wechat_miniprogram_openid=openid,
        )

        with self._users_lock:
            self._create_user(user)

        # 创建会话
        session_token, csrf_token = self._create_session(username, lab.lab_id)

        return {
            "status": "success",
            "session_token": session_token,
            "csrf_token": csrf_token,
            "lab_id": lab.lab_id,
            "lab_name": lab.lab_name,
        }

    # ==================== 辅助方法 ====================

    def _verify_csrf_token(self, body: Dict[str, Any], session_token: str) -> bool:
        """
        验证 CSRF token。

        ✅ P0-3: CSRF 保护
        """
        csrf_token = body.get("csrf_token", "")
        if not csrf_token:
            return False

        session = self._get_session(session_token)
        if not session:
            return False

        # ✅ 使用恒定时间比较
        return hmac.compare_digest(csrf_token, session.csrf_token)

    def _verify_session_and_lab(
        self,
        session_token: str,
        required_lab_id: Optional[str] = None
    ) -> Tuple[Optional[Any], Optional[str]]:
        """
        验证会话并返回用户和 lab_id。

        ✅ P1-6: 统一错误信息
        """
        session = self._get_session(session_token)
        if not session:
            return None, "Authentication failed"

        user = self._find_user_by_username(session.username)
        if not user:
            return None, "Authentication failed"

        if user.account_status != "active":
            return None, "Authentication failed"

        if required_lab_id and session.lab_id != required_lab_id:
            return None, "Authentication failed"

        return user, None

    def _create_user_object(
        self,
        username: str,
        display_name: str,
        role,
        lab_id: str,
        wechat_unionid: str = "",
        wechat_miniprogram_openid: str = "",
    ):
        """创建用户对象（辅助方法）"""
        from .api_extensions import WebUser

        return WebUser(
            username=username,
            password_hash="",
            password_salt="",
            display_name=display_name,
            role=role,
            lab_id=lab_id,
            account_status="active",
            created_at=datetime.now(timezone.utc).isoformat(),
            wechat_unionid=wechat_unionid,
            wechat_miniprogram_openid=wechat_miniprogram_openid,
        )


# ==================== 配置验证 ====================

def validate_config(config) -> None:
    """
    验证配置安全性。

    ✅ P1-5: 配置验证
    """
    # 检查占位符
    placeholder_keywords = ["your_", "example", "test", "demo"]
    for keyword in placeholder_keywords:
        if keyword in config.wechat_miniprogram_appid.lower():
            raise ValueError(
                f"Please configure WECHAT_MINIPROGRAM_APPID in .env file. "
                f"Current value appears to be a placeholder."
            )

    # 检查密钥强度
    if not config.wechat_miniprogram_secret or len(config.wechat_miniprogram_secret) < 16:
        raise ValueError("Invalid WECHAT_MINIPROGRAM_SECRET (minimum 16 characters required)")

    # 检查 AppID 格式
    if not config.wechat_miniprogram_appid.startswith("wx"):
        raise ValueError("Invalid WECHAT_MINIPROGRAM_APPID format (should start with 'wx')")


# ==================== 使用示例 ====================

"""
应用修复的步骤：

1. 在 api_extensions.py 中添加新类：
   - RateLimiter
   - AccountLockManager
   - PendingBindStore
   - InputValidator

2. 修改 APIRequestHandler.__init__：
   添加速率限制器、账号锁定管理器、待绑定会话存储、文件锁

3. 替换 api_wechat_miniprogram_login 方法：
   使用 SecureAPIRequestHandler.api_wechat_miniprogram_login

4. 替换 api_wechat_bind_lab 方法：
   使用 SecureAPIRequestHandler.api_wechat_bind_lab

5. 在 config.py 的 load_config 中添加：
   config = Config(...)
   validate_config(config)
   return config

6. 运行安全测试：
   pytest tests/test_security.py -v

7. 手动渗透测试：
   python -m pytest tests/test_security.py::penetration_test_suite -v
"""
