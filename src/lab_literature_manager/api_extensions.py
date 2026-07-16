"""
API extensions for WeChat login and multi-lab support.

This module provides RESTful API endpoints for:
- WeChat miniprogram/official account login
- Lab (research group) management
- Multi-lab data isolation

To be integrated into web.py or deployed as a standalone API service.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from .models import Lab, Role
from .multilab_repository import MultiLabRepository
from .wechat_api import (
    WeChatAPIError,
    WeChatConfig,
    get_official_account_access_token,
    miniprogram_code_to_session,
)

# 常量定义（避免循环导入）
ACCOUNT_STATUS_ACTIVE = "active"
ACCOUNT_STATUS_PENDING = "pending"
SESSION_COOKIE_NAME = "litman_session"
SESSION_TTL_HOURS = 8

API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"


@dataclass
class WebUser:
    """Web 用户数据类（简化版，避免循环导入）"""
    username: str
    password_hash: str
    password_salt: str
    display_name: str
    role: Role
    member_id: str = ""
    lab_id: str = ""
    created_at: str = ""
    account_status: str = ACCOUNT_STATUS_ACTIVE
    approved_by: str = ""
    approved_at: str = ""
    deletion_requested_at: str = ""
    deletion_approved_by: str = ""
    wechat_unionid: str = ""
    wechat_miniprogram_openid: str = ""
    wechat_officialaccount_openid: str = ""
    wechat_nickname: str = ""
    wechat_avatar: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "password_salt": self.password_salt,
            "display_name": self.display_name,
            "role": self.role.value,
            "member_id": self.member_id,
            "lab_id": self.lab_id,
            "created_at": self.created_at,
            "account_status": self.account_status,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "deletion_requested_at": self.deletion_requested_at,
            "deletion_approved_by": self.deletion_approved_by,
            "wechat_unionid": self.wechat_unionid,
            "wechat_miniprogram_openid": self.wechat_miniprogram_openid,
            "wechat_officialaccount_openid": self.wechat_officialaccount_openid,
            "wechat_nickname": self.wechat_nickname,
            "wechat_avatar": self.wechat_avatar,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "WebUser":
        return cls(
            username=str(data.get("username", "")),
            password_hash=str(data.get("password_hash", "")),
            password_salt=str(data.get("password_salt", "")),
            display_name=str(data.get("display_name", "")),
            role=Role(str(data.get("role", Role.MEMBER.value))),
            member_id=str(data.get("member_id", "")),
            lab_id=str(data.get("lab_id", "")),
            created_at=str(data.get("created_at", "")),
            account_status=str(data.get("account_status", ACCOUNT_STATUS_ACTIVE)),
            approved_by=str(data.get("approved_by", "")),
            approved_at=str(data.get("approved_at", "")),
            deletion_requested_at=str(data.get("deletion_requested_at", "")),
            deletion_approved_by=str(data.get("deletion_approved_by", "")),
            wechat_unionid=str(data.get("wechat_unionid", "")),
            wechat_miniprogram_openid=str(data.get("wechat_miniprogram_openid", "")),
            wechat_officialaccount_openid=str(data.get("wechat_officialaccount_openid", "")),
            wechat_nickname=str(data.get("wechat_nickname", "")),
            wechat_avatar=str(data.get("wechat_avatar", "")),
        )


@dataclass
class APISession:
    """API 会话信息（与 web.py 的 SessionRecord 兼容）"""

    username: str
    lab_id: str
    expires_at: datetime
    csrf_token: str


class APIRequestHandler:
    """
    API 请求处理器（混入类）。

    将此类的方法集成到 web.py 的 WebRequestHandler 中，
    或作为独立 API 服务使用。
    """

    def __init__(
        self,
        multilab_repo: MultiLabRepository,
        wechat_config: WeChatConfig,
        users_file: str,
    ):
        """
        初始化 API 处理器。

        :param multilab_repo: 多课题组仓库
        :param wechat_config: 微信配置
        :param users_file: 用户数据文件路径
        """
        self.multilab_repo = multilab_repo
        self.wechat_config = wechat_config
        self.users_file = users_file
        self._sessions: Dict[str, APISession] = {}
        self._users_cache: Optional[List[WebUser]] = None

    # ==================== 用户管理 ====================

    def _load_users(self) -> List[WebUser]:
        """加载所有用户"""
        import json
        from pathlib import Path

        users_path = Path(self.users_file)
        if not users_path.exists():
            return []

        with open(users_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return [WebUser.from_dict(user_data) for user_data in data]

    def _save_users(self, users: List[WebUser]) -> None:
        """保存用户（原子替换）"""
        import json
        from pathlib import Path

        users_path = Path(self.users_file)
        temp_file = users_path.with_suffix(".tmp")

        with open(temp_file, "w", encoding="utf-8") as f:
            data = [user.to_dict() for user in users]
            json.dump(data, f, ensure_ascii=False, indent=2)

        temp_file.replace(users_path)
        self._users_cache = users

    def _find_user_by_username(self, username: str) -> Optional[WebUser]:
        """根据用户名查找用户"""
        if self._users_cache is None:
            self._users_cache = self._load_users()

        for user in self._users_cache:
            if user.username == username:
                return user
        return None

    def _find_user_by_unionid(self, unionid: str) -> Optional[WebUser]:
        """根据 UnionID 查找用户"""
        if self._users_cache is None:
            self._users_cache = self._load_users()

        for user in self._users_cache:
            if user.wechat_unionid and user.wechat_unionid == unionid:
                return user
        return None

    def _create_user(self, user: WebUser) -> None:
        """创建新用户"""
        if self._users_cache is None:
            self._users_cache = self._load_users()

        self._users_cache.append(user)
        self._save_users(self._users_cache)

    def _update_user(self, updated_user: WebUser) -> None:
        """更新用户"""
        if self._users_cache is None:
            self._users_cache = self._load_users()

        users = [
            updated_user if u.username == updated_user.username else u
            for u in self._users_cache
        ]
        self._save_users(users)

    # ==================== 会话管理 ====================

    def _create_session(self, username: str, lab_id: str) -> Tuple[str, str]:
        """
        创建新会话。

        :return: (session_token, csrf_token)
        """
        session_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(16)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)

        session = APISession(
            username=username,
            lab_id=lab_id,
            expires_at=expires_at,
            csrf_token=csrf_token,
        )
        self._sessions[session_token] = session

        return session_token, csrf_token

    def _get_session(self, session_token: str) -> Optional[APISession]:
        """获取会话信息"""
        session = self._sessions.get(session_token)
        if not session:
            return None

        # 检查是否过期
        if datetime.now(timezone.utc) > session.expires_at:
            del self._sessions[session_token]
            return None

        return session

    def _verify_session_and_lab(
        self, session_token: str, required_lab_id: Optional[str] = None
    ) -> Tuple[Optional[WebUser], Optional[str]]:
        """
        验证会话并返回用户和 lab_id。

        :param session_token: 会话令牌
        :param required_lab_id: 要求的 lab_id（None 表示不检查）
        :return: (WebUser, lab_id) 或 (None, error_message)
        """
        session = self._get_session(session_token)
        if not session:
            return None, "Invalid or expired session"

        user = self._find_user_by_username(session.username)
        if not user:
            return None, "User not found"

        if user.account_status != ACCOUNT_STATUS_ACTIVE:
            return None, "User account is not active"

        if required_lab_id and session.lab_id != required_lab_id:
            return None, "Lab ID mismatch"

        return user, None

    # ==================== API 端点 ====================

    def api_wechat_miniprogram_login(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /api/v1/wechat/miniprogram/login
        小程序登录接口。

        请求体:
        {
            "code": "wx.login() 返回的 code"
        }

        响应:
        {
            "status": "success" | "need_bind",
            "session_token": "...",  # status=success 时返回
            "csrf_token": "...",
            "unionid": "...",        # status=need_bind 时返回
            "openid": "..."
        }
        """
        code = body.get("code", "")
        if not code:
            return {"error": "Missing code parameter"}

        try:
            # 调用微信 API 换取 openid/unionid
            wechat_session = miniprogram_code_to_session(
                self.wechat_config.miniprogram_appid,
                self.wechat_config.miniprogram_secret,
                code,
            )
        except WeChatAPIError as e:
            return {"error": f"WeChat API error: {e.errmsg}"}

        # 优先使用 unionid，没有则使用 openid
        identifier = wechat_session.unionid or wechat_session.openid
        if not identifier:
            return {"error": "Failed to get user identifier from WeChat"}

        # 查找用户
        user = None
        if wechat_session.unionid:
            user = self._find_user_by_unionid(wechat_session.unionid)

        if not user:
            # 尝试通过小程序 openid 查找
            if self._users_cache is None:
                self._users_cache = self._load_users()
            for u in self._users_cache:
                if u.wechat_miniprogram_openid == wechat_session.openid:
                    user = u
                    break

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
            return {
                "status": "need_bind",
                "unionid": wechat_session.unionid,
                "openid": wechat_session.openid,
                "session_key": wechat_session.session_key,
            }

    def api_wechat_bind_lab(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /api/v1/wechat/bind
        绑定课题组接口。

        请求体:
        {
            "unionid": "...",
            "openid": "...",
            "source": "miniprogram" | "official_account",
            "invite_code": "...",  # 加入现有课题组
            "display_name": "..."
        }

        或者创建新课题组:
        {
            "unionid": "...",
            "openid": "...",
            "source": "miniprogram",
            "create_lab": true,
            "lab_name": "...",
            "lab_subtitle": "...",
            "display_name": "..."
        }
        """
        unionid = body.get("unionid", "")
        openid = body.get("openid", "")
        source = body.get("source", "miniprogram")
        display_name = body.get("display_name", "")

        if not openid:
            return {"error": "Missing openid parameter"}

        if not display_name:
            display_name = f"用户_{openid[:8]}"

        # 检查是否创建新课题组
        if body.get("create_lab"):
            lab_name = body.get("lab_name", "")
            if not lab_name:
                return {"error": "Missing lab_name parameter"}

            lab_subtitle = body.get("lab_subtitle", "")
            username = f"wechat_{openid[:16]}"

            # 创建新课题组
            lab = self.multilab_repo.create_lab(
                lab_name=lab_name,
                lab_subtitle=lab_subtitle,
                admin_username=username,
            )

            # 创建管理员用户
            user = WebUser(
                username=username,
                password_hash="",
                password_salt="",
                display_name=display_name,
                role=Role.ADMIN,
                lab_id=lab.lab_id,
                account_status=ACCOUNT_STATUS_ACTIVE,
                wechat_unionid=unionid,
                wechat_miniprogram_openid=openid if source == "miniprogram" else "",
                wechat_officialaccount_openid=openid if source == "official_account" else "",
            )
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
        invite_code = body.get("invite_code", "")
        if not invite_code:
            return {"error": "Missing invite_code parameter"}

        lab = self.multilab_repo.find_lab_by_invite_code(invite_code)
        if not lab:
            return {"error": "Invalid invite code"}

        username = f"wechat_{openid[:16]}"

        # 创建成员用户
        user = WebUser(
            username=username,
            password_hash="",
            password_salt="",
            display_name=display_name,
            role=Role.MEMBER,
            lab_id=lab.lab_id,
            account_status=ACCOUNT_STATUS_ACTIVE,
            wechat_unionid=unionid,
            wechat_miniprogram_openid=openid if source == "miniprogram" else "",
            wechat_officialaccount_openid=openid if source == "official_account" else "",
        )
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

    def api_labs_list(self, session_token: str) -> Dict[str, Any]:
        """
        GET /api/v1/labs
        列出用户可访问的课题组。
        """
        user, error = self._verify_session_and_lab(session_token)
        if error:
            return {"error": error}

        # 目前只返回用户所属的课题组
        lab = self.multilab_repo.get_lab(user.lab_id)
        if not lab:
            return {"error": "Lab not found"}

        return {
            "labs": [
                {
                    "lab_id": lab.lab_id,
                    "lab_name": lab.lab_name,
                    "lab_subtitle": lab.lab_subtitle,
                    "role": user.role.value,
                }
            ]
        }

    def api_lab_info(self, session_token: str, lab_id: str) -> Dict[str, Any]:
        """
        GET /api/v1/labs/:lab_id
        获取课题组信息。
        """
        user, error = self._verify_session_and_lab(session_token, lab_id)
        if error:
            return {"error": error}

        lab = self.multilab_repo.get_lab(lab_id)
        if not lab:
            return {"error": "Lab not found"}

        return {
            "lab_id": lab.lab_id,
            "lab_name": lab.lab_name,
            "lab_subtitle": lab.lab_subtitle,
            "created_at": lab.created_at,
            "invite_code": lab.invite_code if user.role in (Role.ADMIN, Role.PI) else "",
        }

    def api_lab_regenerate_invite_code(
        self, session_token: str, lab_id: str
    ) -> Dict[str, Any]:
        """
        POST /api/v1/labs/:lab_id/regenerate_invite_code
        重新生成邀请码（仅管理员）。
        """
        user, error = self._verify_session_and_lab(session_token, lab_id)
        if error:
            return {"error": error}

        if user.role not in (Role.ADMIN, Role.PI):
            return {"error": "Permission denied"}

        try:
            new_invite_code = self.multilab_repo.regenerate_invite_code(lab_id)
            return {"invite_code": new_invite_code}
        except ValueError as e:
            return {"error": str(e)}
