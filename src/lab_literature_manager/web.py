"""Local browser UI for the research output manager."""

from __future__ import annotations

import base64
import cgi
import hashlib
import hmac
import html
import json
import random
import secrets
import threading
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, quote, unquote, urlparse

from .data_fetcher import DocumentImportDraft, fetch_article_metadata, infer_document_draft
from .models import (
    ArticleMetadata,
    Member,
    OutputType,
    PatentMetadata,
    Permission,
    Project,
    ResearchOutput,
    ReviewStatus,
    Role,
    output_type_label,
    review_status_label,
    role_label,
)
from .permissions import can_perform
from .repository import ResearchRepository

AUTH_SCHEMA_VERSION = 1
SESSION_COOKIE_NAME = "litman_session"
SESSION_TTL_HOURS = 8
PASSWORD_ITERATIONS = 180_000
CAPTCHA_TTL_MINUTES = 10
CAPTCHA_DIGITS = 4
ACCOUNT_STATUS_ACTIVE = "active"
ACCOUNT_STATUS_PENDING = "pending"
DEFAULT_WORKSPACE_NAME = "科研成果管理系统"
WORKSPACE_SETTINGS_FILE = "workspace_settings.json"


@dataclass(frozen=True)
class WorkspaceSettings:
    workspace_name: str = DEFAULT_WORKSPACE_NAME
    workspace_subtitle: str = "成果管理与审核工作台"

    def to_dict(self) -> Dict[str, str]:
        return {
            "workspace_name": self.workspace_name,
            "workspace_subtitle": self.workspace_subtitle,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "WorkspaceSettings":
        workspace_name = str(data.get("workspace_name", DEFAULT_WORKSPACE_NAME)).strip()
        workspace_subtitle = str(data.get("workspace_subtitle", "成果管理与审核工作台")).strip()
        return cls(
            workspace_name=workspace_name or DEFAULT_WORKSPACE_NAME,
            workspace_subtitle=workspace_subtitle or "成果管理与审核工作台",
        )


@dataclass(frozen=True)
class WebUser:
    username: str
    password_hash: str
    password_salt: str
    display_name: str
    role: Role
    member_id: str = ""
    created_at: str = ""
    account_status: str = ACCOUNT_STATUS_ACTIVE
    approved_by: str = ""
    approved_at: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "password_salt": self.password_salt,
            "display_name": self.display_name,
            "role": self.role.value,
            "member_id": self.member_id,
            "created_at": self.created_at,
            "account_status": self.account_status,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
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
            created_at=str(data.get("created_at", "")),
            account_status=str(data.get("account_status", ACCOUNT_STATUS_ACTIVE)),
            approved_by=str(data.get("approved_by", "")),
            approved_at=str(data.get("approved_at", "")),
        )


@dataclass
class SessionRecord:
    username: str
    expires_at: datetime


@dataclass
class CaptchaChallenge:
    token: str
    answer: str
    expires_at: datetime


class LoginCaptchaStore:
    """In-memory login captcha registry."""

    def __init__(self) -> None:
        self._challenges: Dict[str, CaptchaChallenge] = {}
        self._lock = threading.Lock()

    def issue(self) -> CaptchaChallenge:
        token = secrets.token_urlsafe(24)
        answer = "".join(str(secrets.randbelow(10)) for _ in range(CAPTCHA_DIGITS))
        challenge = CaptchaChallenge(
            token=token,
            answer=answer,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=CAPTCHA_TTL_MINUTES),
        )
        with self._lock:
            self._challenges[token] = challenge
        return challenge

    def verify(self, token: str, answer: str) -> bool:
        normalized_token = token.strip()
        normalized_answer = answer.strip()
        if not normalized_token or not normalized_answer:
            return False
        with self._lock:
            challenge = self._challenges.pop(normalized_token, None)
        if challenge is None:
            return False
        if challenge.expires_at <= datetime.now(timezone.utc):
            return False
        return hmac.compare_digest(challenge.answer, normalized_answer)


class LocalAuthStore:
    """File-backed local authentication store."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def has_users(self) -> bool:
        return bool(self.list_users())

    def list_users(self) -> List[WebUser]:
        payload = self._load_payload()
        return [WebUser.from_dict(item) for item in payload.get("items", [])]

    def list_pending_users(self) -> List[WebUser]:
        return [user for user in self.list_users() if user.account_status == ACCOUNT_STATUS_PENDING]

    def get_user(self, username: str) -> Optional[WebUser]:
        normalized = username.strip()
        for user in self.list_users():
            if user.username == normalized:
                return user
        return None

    def create_user(
        self,
        username: str,
        password: str,
        *,
        display_name: str,
        role: Role,
        member_id: str = "",
        account_status: str = ACCOUNT_STATUS_ACTIVE,
    ) -> WebUser:
        normalized_username = username.strip()
        normalized_password = password.strip()
        normalized_display_name = display_name.strip()
        if not normalized_username:
            raise ValueError("Username must not be empty.")
        if not normalized_password:
            raise ValueError("Password must not be empty.")
        if not normalized_display_name:
            raise ValueError("Display name must not be empty.")

        with self._lock:
            users = self.list_users()
            if any(user.username == normalized_username for user in users):
                raise ValueError(f"User already exists: {normalized_username}")
            salt = secrets.token_bytes(16)
            user = WebUser(
                username=normalized_username,
                password_hash=self._hash_password(normalized_password, salt),
                password_salt=base64.b64encode(salt).decode("ascii"),
                display_name=normalized_display_name,
                role=role if isinstance(role, Role) else Role(str(role)),
                member_id=member_id.strip() or normalized_username,
                created_at=self._now_iso(),
                account_status=account_status,
            )
            users.append(user)
            self._save_users(users)
            return user

    def authenticate(self, username: str, password: str) -> Optional[WebUser]:
        user = self.get_user(username)
        if user is None:
            return None
        if user.account_status != ACCOUNT_STATUS_ACTIVE:
            return None
        if self.is_password_valid(user, password):
            return user
        return None

    def is_password_valid(self, user: WebUser, password: str) -> bool:
        salt = base64.b64decode(user.password_salt.encode("ascii"))
        expected = user.password_hash
        actual = self._hash_password(password, salt)
        return hmac.compare_digest(expected, actual)

    def approve_user(self, username: str, *, approved_by: str) -> WebUser:
        normalized = username.strip()
        if not normalized:
            raise ValueError("Username must not be empty.")
        with self._lock:
            users = self.list_users()
            updated_users: List[WebUser] = []
            approved: Optional[WebUser] = None
            for user in users:
                if user.username == normalized:
                    approved = replace(
                        user,
                        account_status=ACCOUNT_STATUS_ACTIVE,
                        approved_by=approved_by.strip(),
                        approved_at=self._now_iso(),
                    )
                    updated_users.append(approved)
                else:
                    updated_users.append(user)
            if approved is None:
                raise KeyError(f"User not found: {normalized}")
            self._save_users(updated_users)
            return approved

    def update_user(self, user: WebUser) -> WebUser:
        normalized = user.username.strip()
        with self._lock:
            users = self.list_users()
            if not any(item.username == normalized for item in users):
                raise KeyError(f"User not found: {normalized}")
            updated_users = [user if item.username == normalized else item for item in users]
            self._save_users(updated_users)
            return user

    def _load_payload(self) -> Dict[str, object]:
        if not self.path.exists():
            return {"schema_version": AUTH_SCHEMA_VERSION, "items": []}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Auth file is not valid JSON: {self.path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Auth file must contain a JSON object: {self.path}")
        if payload.get("schema_version") != AUTH_SCHEMA_VERSION:
            raise ValueError(f"Unsupported auth schema version in {self.path}: {payload.get('schema_version')}")
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise ValueError(f"Auth file items must be a JSON list: {self.path}")
        return payload

    def _save_users(self, users: Iterable[WebUser]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": AUTH_SCHEMA_VERSION,
            "items": [user.to_dict() for user in sorted(users, key=lambda item: item.username.lower())],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _hash_password(password: str, salt: bytes) -> str:
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            PASSWORD_ITERATIONS,
        )
        return base64.b64encode(derived).decode("ascii")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class SessionStore:
    """In-memory session registry."""

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionRecord] = {}
        self._lock = threading.Lock()

    def create(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
        with self._lock:
            self._sessions[token] = SessionRecord(username=username, expires_at=expires_at)
        return token

    def get(self, token: str) -> Optional[str]:
        normalized = token.strip()
        if not normalized:
            return None
        with self._lock:
            record = self._sessions.get(normalized)
            if record is None:
                return None
            if record.expires_at <= datetime.now(timezone.utc):
                self._sessions.pop(normalized, None)
                return None
            record.expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
            return record.username

    def revoke(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token.strip(), None)


class WebApplication:
    """Stateful browser application on top of the repository."""

    def __init__(self, data_dir: Path | str, auth_path: Path | str) -> None:
        self.repository = ResearchRepository(data_dir)
        self.auth_store = LocalAuthStore(auth_path)
        self.sessions = SessionStore()
        self.login_captchas = LoginCaptchaStore()
        self.settings_path = Path(data_dir) / WORKSPACE_SETTINGS_FILE

    def load_settings(self) -> WorkspaceSettings:
        if not self.settings_path.exists():
            return WorkspaceSettings()
        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Workspace settings file is not valid JSON: {self.settings_path}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Workspace settings file must contain a JSON object: {self.settings_path}")
        return WorkspaceSettings.from_dict(payload)

    def save_settings(self, settings: WorkspaceSettings) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(settings.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def issue_login_captcha(self) -> CaptchaChallenge:
        return self.login_captchas.issue()

    def authenticate_with_captcha(
        self,
        username: str,
        password: str,
        captcha_token: str,
        captcha_answer: str,
    ) -> Optional[WebUser]:
        if not self.login_captchas.verify(captcha_token, captcha_answer):
            return None
        return self.auth_store.authenticate(username, password)

    def promote_member_to_admin(self, member_id: str, *, actor: WebUser) -> Member:
        if actor.role not in {Role.ADMIN, Role.PI}:
            raise PermissionError("当前账号没有提权权限。")
        member = self.repository.get_member(member_id)
        updated_member = replace(member, role=Role.ADMIN)
        self.repository.update_member(updated_member)
        user = self.auth_store.get_user(member.member_id)
        if user is not None:
            promoted_user = replace(user, role=Role.ADMIN)
            self.auth_store.update_user(promoted_user)
        return updated_member

    def get_current_user(self, handler: BaseHTTPRequestHandler) -> Optional[WebUser]:
        token = self._get_cookie(handler, SESSION_COOKIE_NAME)
        if not token:
            return None
        username = self.sessions.get(token)
        if not username:
            return None
        return self.auth_store.get_user(username)

    def redirect(self, handler: BaseHTTPRequestHandler, location: str) -> None:
        handler.send_response(303)
        handler.send_header("Location", location)
        handler.send_header("Content-Length", "0")
        handler.end_headers()

    def render_layout(
        self,
        title: str,
        body: str,
        *,
        active_section: str = "",
        current_user: Optional[WebUser] = None,
        notice: str = "",
        public_page: bool = False,
    ) -> str:
        settings = self.load_settings()
        nav = self._render_nav(active_section=active_section, current_user=current_user, settings=settings)
        notice_html = f'<div class="notice">{html.escape(notice)}</div>' if notice else ""
        if public_page:
            page_body = f"{notice_html}{body}"
        else:
            page_body = f"""
  {notice_html}
  <div class="shell">
    {nav}
    <main class="content">
      {body}
    </main>
  </div>"""
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #f4f1ea;
      --panel: #ffffff;
      --panel-soft: #f8f7f2;
      --text: #122018;
      --muted: #5d6b66;
      --line: rgba(18, 32, 24, 0.12);
      --accent: #0f766e;
      --accent-strong: #115e59;
      --accent-soft: rgba(15, 118, 110, 0.12);
      --gold: #c28a1a;
      --danger: #b45309;
      --shadow: 0 18px 50px rgba(18, 32, 24, 0.08);
      --radius: 20px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(15,118,110,0.12), transparent 35%),
        radial-gradient(circle at top right, rgba(194,138,26,0.11), transparent 30%),
        linear-gradient(180deg, #faf8f3 0%, var(--bg) 100%);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    a {{ color: inherit; text-decoration: none; }}
    .shell {{
      min-height: 100vh;
      display: grid;
      grid-template-columns: 260px 1fr;
    }}
    .sidebar {{
      padding: 28px 22px;
      background: rgba(255, 255, 255, 0.72);
      border-right: 1px solid var(--line);
      backdrop-filter: blur(10px);
    }}
    .brand {{
      display: flex;
      gap: 12px;
      align-items: center;
      margin-bottom: 28px;
    }}
    .brand-mark {{
      width: 42px;
      height: 42px;
      border-radius: 14px;
      background: linear-gradient(135deg, var(--accent), var(--gold));
      box-shadow: var(--shadow);
    }}
    .brand h1 {{
      margin: 0;
      font-size: 1rem;
      line-height: 1.2;
    }}
    .brand p {{
      margin: 3px 0 0;
      color: var(--muted);
      font-size: 0.84rem;
    }}
    .nav-section {{
      display: grid;
      gap: 8px;
      margin-top: 18px;
    }}
    .nav-link {{
      padding: 11px 14px;
      border-radius: 14px;
      color: var(--muted);
      border: 1px solid transparent;
    }}
    .nav-link.active, .nav-link:hover {{
      color: var(--text);
      background: var(--panel);
      border-color: var(--line);
      box-shadow: 0 8px 24px rgba(18, 32, 24, 0.06);
    }}
    .content {{
      padding: 28px;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      margin-bottom: 22px;
    }}
    .topbar h2 {{
      margin: 0;
      font-size: 1.8rem;
      letter-spacing: -0.03em;
    }}
    .topbar .subtle {{
      margin-top: 6px;
      color: var(--muted);
    }}
    .user-pill {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-radius: 999px;
      background: rgba(255,255,255,0.86);
      border: 1px solid var(--line);
      box-shadow: 0 10px 30px rgba(18, 32, 24, 0.05);
    }}
    .avatar {{
      width: 30px;
      height: 30px;
      border-radius: 999px;
      display: grid;
      place-items: center;
      color: white;
      font-size: 0.85rem;
      background: linear-gradient(135deg, var(--accent-strong), var(--accent));
    }}
    .grid {{
      display: grid;
      gap: 18px;
    }}
    .cards {{
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }}
    .card {{
      background: rgba(255,255,255,0.9);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 18px;
    }}
    .metric-label {{
      color: var(--muted);
      font-size: 0.9rem;
      margin-bottom: 10px;
    }}
    .metric-value {{
      font-size: 2rem;
      font-weight: 700;
      letter-spacing: -0.04em;
    }}
    .metric-hint {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 0.86rem;
    }}
    .panels {{
      grid-template-columns: 1.4fr 0.9fr;
      align-items: start;
    }}
    .panel-title {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
      margin-bottom: 14px;
    }}
    .panel-title h3 {{
      margin: 0;
      font-size: 1.1rem;
    }}
    .panel-title span {{
      color: var(--muted);
      font-size: 0.87rem;
    }}
    .bar-chart {{
      display: grid;
      gap: 12px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 160px 1fr 56px;
      gap: 12px;
      align-items: center;
    }}
    .bar-track {{
      height: 12px;
      border-radius: 999px;
      background: #e9ece7;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent), #47b4a7);
    }}
    .status-fill {{
      background: linear-gradient(90deg, var(--gold), #e2b04b);
    }}
    .table {{
      width: 100%;
      border-collapse: collapse;
    }}
    .table th, .table td {{
      text-align: left;
      padding: 12px 10px;
      border-top: 1px solid var(--line);
      vertical-align: top;
    }}
    .table th {{
      color: var(--muted);
      font-size: 0.84rem;
      letter-spacing: 0.03em;
      text-transform: uppercase;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 0.82rem;
      background: var(--accent-soft);
      color: var(--accent-strong);
    }}
    .badge.status-submitted, .badge.status-approved {{
      background: rgba(194, 138, 26, 0.14);
      color: #8b5e12;
    }}
    .badge.status-returned {{
      background: rgba(180, 83, 9, 0.12);
      color: var(--danger);
    }}
    .login-shell {{
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 28px;
    }}
    .login-card {{
      width: min(940px, 100%);
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      background: rgba(255,255,255,0.9);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .login-card.compact {{
      width: min(420px, 100%);
      display: block;
      border-radius: 22px;
    }}
    .login-hero {{
      padding: 34px;
      background:
        radial-gradient(circle at top left, rgba(15,118,110,0.16), transparent 38%),
        linear-gradient(135deg, #123127 0%, #183d31 60%, #244834 100%);
      color: white;
    }}
    .login-hero h1 {{
      margin: 0 0 14px;
      font-size: 2.2rem;
      letter-spacing: -0.04em;
    }}
    .login-hero p {{
      margin: 0 0 24px;
      color: rgba(255,255,255,0.82);
      max-width: 34ch;
      line-height: 1.6;
    }}
    .login-badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255,255,255,0.12);
      border: 1px solid rgba(255,255,255,0.16);
      font-size: 0.82rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }}
    .login-hero-grid {{
      display: grid;
      gap: 16px;
    }}
    .login-hero-panel {{
      padding: 16px;
      border-radius: 20px;
      background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.12);
    }}
    .login-hero-panel h3 {{
      margin: 0 0 8px;
      font-size: 0.98rem;
    }}
    .login-hero-panel p {{
      margin: 0;
      max-width: none;
    }}
    .login-stats {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .login-stat {{
      padding: 14px;
      border-radius: 18px;
      background: rgba(255,255,255,0.09);
      border: 1px solid rgba(255,255,255,0.13);
    }}
    .login-stat strong {{
      display: block;
      font-size: 1.25rem;
      margin-bottom: 6px;
    }}
    .login-entry-list {{
      display: grid;
      gap: 12px;
      margin-bottom: 22px;
    }}
    .login-entry {{
      padding: 14px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: var(--panel-soft);
    }}
    .login-entry strong {{
      display: block;
      margin-bottom: 4px;
    }}
    .login-entry span {{
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.5;
    }}
    .captcha-panel {{
      min-width: 132px;
      display: inline-flex;
      justify-content: center;
      align-items: center;
      border-radius: 14px;
      border: 1px solid var(--line);
      background:
        linear-gradient(135deg, rgba(15,118,110,0.08), rgba(194,138,26,0.12)),
        #fff;
      padding: 12px 14px;
      letter-spacing: 0.25em;
      font-weight: 700;
      color: var(--accent-strong);
      user-select: none;
      font-variant-numeric: tabular-nums;
    }}
    .captcha-digits {{
      font-size: 1.1rem;
    }}
    .login-panel {{
      padding: 34px;
    }}
    .field {{
      margin-bottom: 16px;
    }}
    label {{
      display: block;
      margin-bottom: 8px;
      font-size: 0.92rem;
      color: var(--muted);
    }}
    input, select, textarea, button {{
      font: inherit;
    }}
    input, textarea {{
      width: 100%;
      border-radius: 14px;
      border: 1px solid var(--line);
      padding: 12px 14px;
      background: #fff;
      color: var(--text);
    }}
    input:focus, textarea:focus {{
      outline: none;
      border-color: rgba(15,118,110,0.45);
      box-shadow: 0 0 0 4px rgba(15,118,110,0.12);
    }}
    .button-row {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .button {{
      display: inline-flex;
      justify-content: center;
      align-items: center;
      gap: 8px;
      padding: 11px 16px;
      border-radius: 14px;
      border: 1px solid transparent;
      cursor: pointer;
      text-decoration: none;
    }}
    .button.primary {{
      background: var(--accent);
      color: white;
    }}
    .button.secondary {{
      background: rgba(255,255,255,0.86);
      border-color: var(--line);
      color: var(--text);
    }}
    .button.ghost {{
      background: transparent;
      border-color: var(--line);
      color: var(--text);
    }}
    .split-field {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: end;
    }}
    .inline-help {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 0.85rem;
      line-height: 1.5;
    }}
    .section-banner {{
      display: grid;
      gap: 6px;
      margin-bottom: 18px;
    }}
    .section-banner h2, .section-banner h3 {{
      margin: 0;
    }}
    .section-banner p {{
      margin: 0;
      color: var(--muted);
    }}
    .workflow-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }}
    .workflow-card {{
      padding: 16px;
      border-radius: 18px;
      background: rgba(255,255,255,0.82);
      border: 1px solid var(--line);
    }}
    .workflow-card strong {{
      display: block;
      margin-bottom: 6px;
    }}
    .workflow-card span {{
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.5;
    }}
    .stack {{
      display: grid;
      gap: 14px;
    }}
    .notice {{
      margin-bottom: 18px;
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(15,118,110,0.1);
      border: 1px solid rgba(15,118,110,0.18);
      color: var(--accent-strong);
    }}
    .muted {{
      color: var(--muted);
    }}
    .detail-grid {{
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 18px;
    }}
    .form-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }}
    .form-grid .field {{
      margin-bottom: 0;
    }}
    .form-grid .span-2 {{
      grid-column: 1 / -1;
    }}
    .kv {{
      display: grid;
      gap: 8px;
    }}
    .kv div {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 10px 0;
      border-top: 1px solid var(--line);
    }}
    .kv span:first-child {{
      color: var(--muted);
    }}
    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .chip {{
      padding: 7px 11px;
      border-radius: 999px;
      background: rgba(18, 32, 24, 0.06);
      color: var(--text);
      font-size: 0.84rem;
    }}
    .source-card {{
      padding: 14px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: var(--panel-soft);
    }}
    .source-card h3 {{
      margin: 0 0 10px;
      font-size: 1rem;
    }}
    .source-card p {{
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.5;
    }}
    .empty-state {{
      padding: 22px;
      border-radius: 18px;
      border: 1px dashed var(--line);
      color: var(--muted);
      background: rgba(255,255,255,0.62);
    }}
    @media (max-width: 1080px) {{
      .shell {{ grid-template-columns: 1fr; }}
      .sidebar {{ border-right: none; border-bottom: 1px solid var(--line); }}
      .cards, .panels, .detail-grid, .login-card, .workflow-grid, .form-grid {{ grid-template-columns: 1fr; }}
      .bar-row {{ grid-template-columns: 1fr; }}
      .content {{ padding: 18px; }}
      .split-field {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  {page_body}
</body>
</html>"""

    def _render_nav(
        self,
        *,
        active_section: str,
        current_user: Optional[WebUser],
        settings: WorkspaceSettings,
    ) -> str:
        if current_user is None:
            if self.auth_store.has_users():
                return ""
            return ""
        links = [
            ("dashboard", "/", "仪表盘"),
            ("outputs", "/outputs", "成果管理"),
            ("logout", "/logout", "退出登录"),
        ]
        if current_user.role in {Role.ADMIN, Role.PI}:
            links.insert(1, ("members", "/members", "成员管理"))
            links.insert(2, ("projects", "/projects", "项目管理"))
            links.insert(2, ("reviews", "/reviews", "审核工作台"))
            links.insert(3, ("accounts", "/accounts/pending", "账号审核"))
        items = []
        for section, href, label in links:
            active = " active" if active_section == section else ""
            items.append(f'<a class="nav-link{active}" href="{href}">{html.escape(label)}</a>')
        avatar = current_user.display_name[:1].upper() if current_user.display_name else current_user.username[:1].upper()
        return f"""
        <aside class="sidebar">
          <div class="brand">
            <div class="brand-mark"></div>
            <div>
              <h1>{html.escape(settings.workspace_name)}</h1>
              <p>{html.escape(settings.workspace_subtitle)}</p>
            </div>
          </div>
          <div class="user-pill">
            <div class="avatar">{html.escape(avatar)}</div>
            <div>
              <strong>{html.escape(current_user.display_name)}</strong><br />
              <span class="muted">{html.escape(role_label(current_user.role))}</span>
            </div>
          </div>
          <nav class="nav-section">{''.join(items)}</nav>
        </aside>
        """

    def _get_cookie(self, handler: BaseHTTPRequestHandler, name: str) -> str:
        raw = handler.headers.get("Cookie", "")
        jar = cookies.SimpleCookie()
        jar.load(raw)
        morsel = jar.get(name)
        return morsel.value if morsel else ""

    def set_session_cookie(self, handler: BaseHTTPRequestHandler, token: str) -> None:
        cookie = cookies.SimpleCookie()
        cookie[SESSION_COOKIE_NAME] = token
        cookie[SESSION_COOKIE_NAME]["path"] = "/"
        cookie[SESSION_COOKIE_NAME]["httponly"] = True
        cookie[SESSION_COOKIE_NAME]["samesite"] = "Lax"
        expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)
        cookie[SESSION_COOKIE_NAME]["expires"] = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
        handler.send_header("Set-Cookie", cookie.output(header="").strip())

    def clear_session_cookie(self, handler: BaseHTTPRequestHandler) -> None:
        cookie = cookies.SimpleCookie()
        cookie[SESSION_COOKIE_NAME] = ""
        cookie[SESSION_COOKIE_NAME]["path"] = "/"
        cookie[SESSION_COOKIE_NAME]["httponly"] = True
        cookie[SESSION_COOKIE_NAME]["samesite"] = "Lax"
        cookie[SESSION_COOKIE_NAME]["max-age"] = 0
        handler.send_header("Set-Cookie", cookie.output(header="").strip())

    def render_login_page(self, error: str = "") -> str:
        error_html = f'<div class="notice">{html.escape(error)}</div>' if error else ""
        settings = self.load_settings()
        challenge = self.issue_login_captcha()
        body = f"""
        <div class="login-shell">
          <section class="login-card compact">
            <div class="login-panel">
              <div class="brand" style="margin-bottom: 24px;">
                <div class="brand-mark"></div>
                <div>
                  <h1>{html.escape(settings.workspace_name)}</h1>
                  <p>{html.escape(settings.workspace_subtitle)}</p>
                </div>
              </div>
              <h2 style="margin:0 0 10px;">登录</h2>
              {error_html}
              <form method="post" action="/login">
                <div class="field">
                  <label for="username">账号</label>
                  <input id="username" name="username" autocomplete="username" required />
                </div>
                <div class="field">
                  <label for="password">密码</label>
                  <input id="password" name="password" type="password" autocomplete="current-password" required />
                </div>
                <input type="hidden" name="captcha_token" value="{html.escape(challenge.token)}" />
                <div class="field">
                  <label for="captcha_answer">验证码</label>
                  <div class="split-field">
                    <input id="captcha_answer" name="captcha_answer" inputmode="numeric" autocomplete="one-time-code" maxlength="{CAPTCHA_DIGITS}" required />
                    <div class="captcha-panel" aria-label="验证码图形">
                      <span class="captcha-digits">{html.escape(challenge.answer)}</span>
                    </div>
                  </div>
                  <div class="inline-help">请输入右侧 4 位数字验证码。</div>
                </div>
                <div class="button-row">
                  <button class="button primary" type="submit">登录</button>
                  <a class="button secondary" href="/register">注册</a>
                </div>
              </form>
            </div>
          </section>
        </div>
        """
        return self.render_layout("登录", body, public_page=True)

    def render_register_page(self, error: str = "", notice: str = "") -> str:
        error_html = f'<div class="notice">{html.escape(error)}</div>' if error else ""
        notice_html = f'<div class="notice">{html.escape(notice)}</div>' if notice else ""
        settings = self.load_settings()
        body = f"""
        <div class="login-shell">
          <section class="login-card compact">
            <div class="login-panel">
              <div class="brand" style="margin-bottom: 24px;">
                <div class="brand-mark"></div>
                <div>
                  <h1>{html.escape(settings.workspace_name)}</h1>
                  <p>新账号需要管理员审核</p>
                </div>
              </div>
              <h2 style="margin:0 0 10px;">注册</h2>
              {notice_html}
              {error_html}
              <form method="post" action="/register">
                <div class="field">
                  <label for="display_name">姓名</label>
                  <input id="display_name" name="display_name" autocomplete="name" required />
                </div>
                <div class="field">
                  <label for="password">密码</label>
                  <input id="password" name="password" type="password" autocomplete="new-password" required />
                </div>
                <div class="button-row">
                  <button class="button primary" type="submit">提交注册</button>
                  <a class="button secondary" href="/login">返回登录</a>
                </div>
              </form>
            </div>
          </section>
        </div>
        """
        return self.render_layout("注册", body, public_page=True)

    def render_setup_page(self, error: str = "") -> str:
        error_html = f'<div class="notice">{html.escape(error)}</div>' if error else ""
        body = f"""
        <div class="login-shell">
          <section class="login-card">
            <div class="login-hero">
              <div class="brand" style="margin-bottom: 30px;">
                <div class="brand-mark"></div>
                <div>
                  <h1>{html.escape(DEFAULT_WORKSPACE_NAME)}</h1>
                  <p>成果管理与审核平台</p>
                </div>
              </div>
              <div class="login-badge">首次初始化</div>
              <h1>创建工作区和第一位管理员。</h1>
              <p>首次进入时设置组织名称、工作台副标题，并创建管理员账号，之后管理员和普通成员就可以按权限进入各自的工作区。</p>
              <div class="login-hero-panel">
                <h3>建议</h3>
                <p>管理员账号只用于工作区初始化，不建议与个人成员账号混用。</p>
              </div>
            </div>
            <div class="login-panel">
              <h2 style="margin:0 0 10px;">工作区设置</h2>
              {error_html}
              <form method="post" action="/setup">
                <div class="field">
                  <label for="workspace_name">组织名称</label>
                  <input id="workspace_name" name="workspace_name" value="{html.escape(DEFAULT_WORKSPACE_NAME)}" placeholder="例如：马老师课题组、科研成果管理系统" required />
                </div>
                <div class="field">
                  <label for="workspace_subtitle">工作台副标题</label>
                  <input id="workspace_subtitle" name="workspace_subtitle" value="成果管理与审核工作台" placeholder="例如：成果管理与审核平台" required />
                </div>
                <div class="field">
                  <label for="username">管理员用户名</label>
                  <input id="username" name="username" autocomplete="username" required />
                </div>
                <div class="field">
                  <label for="display_name">显示名称</label>
                  <input id="display_name" name="display_name" autocomplete="name" required />
                </div>
                <div class="field">
                  <label for="password">密码</label>
                  <input id="password" name="password" type="password" autocomplete="new-password" required />
                </div>
                <div class="button-row">
                  <button class="button primary" type="submit">创建管理员</button>
                </div>
              </form>
            </div>
          </section>
        </div>
        """
        return self.render_layout("工作区设置", body, public_page=True)

    def render_dashboard(self, current_user: WebUser) -> str:
        outputs = self.repository.list_outputs_for_actor(current_user.role, current_user.member_id)
        members = self.repository.list_members()
        projects = self.repository.list_projects()
        recent_outputs = outputs[:5]
        type_counts = self._count_labels((output_type_label(output.output_type) for output in outputs))
        status_counts = self._count_labels((review_status_label(output.review_status) for output in outputs))
        year_counts = self._count_labels((str(output.year) for output in outputs if output.year is not None))
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>成果指挥中心</h2>
              <div class="subtle">浏览成果、跟踪状态、查看分布图。</div>
            </div>
            <div class="button-row">
              <a class="button secondary" href="/outputs">查看成果</a>
              {self._export_button(current_user)}
            </div>
          </div>
          <div class="grid cards">
            {self._metric_card("总成果数", str(len(outputs)), "当前账号可见成果")}
            {self._metric_card("成员数", str(len(members)), "本地成员档案")}
            {self._metric_card("项目数", str(len(projects)), "关联项目与课题")}
            {self._metric_card("已审核", str(status_counts.get(review_status_label(ReviewStatus.APPROVED), 0)), "已通过审核")}
          </div>
          <div class="grid panels">
            <article class="card">
              <div class="panel-title">
                <h3>成果类型分布</h3>
                <span>数量分布</span>
              </div>
              {self._bar_chart(type_counts, accent_class="")}
            </article>
            <article class="card">
              <div class="panel-title">
                <h3>审核状态</h3>
                <span>流程状态</span>
              </div>
              {self._bar_chart(status_counts, accent_class="status-fill")}
              <div style="height:16px"></div>
              <div class="panel-title">
                <h3>年度成果分布</h3>
                <span>发表/归档时间</span>
              </div>
              {self._bar_chart(year_counts, accent_class="")}
            </article>
          </div>
          <article class="card">
            <div class="panel-title">
              <h3>最近成果</h3>
              <span>最新记录</span>
            </div>
            {self._output_table(recent_outputs)}
          </article>
        </section>
        """
        return self.render_layout("仪表盘", body, active_section="dashboard", current_user=current_user)

    def render_members_page(self, current_user: WebUser) -> str:
        members = self.repository.list_members()
        rows = "".join(
            f"<tr>"
            f"<td><a href=\"/members/{html.escape(member.member_id)}\">{html.escape(member.member_id)}</a></td>"
            f"<td>{html.escape(member.name)}</td>"
            f"<td>{html.escape(role_label(member.role))}</td>"
            f"<td>{html.escape(member.email or '-')}</td>"
            f"<td>"
            + (
                ""
                if member.role == Role.ADMIN
                else f'<form method="post" action="/members/{html.escape(member.member_id)}/promote" style="display:inline-block;"><button class="button secondary" type="submit">设为管理员</button></form>'
            )
            + f"</td>"
            f"</tr>"
            for member in members
        ) or '<tr><td colspan="5" class="muted">暂无成员数据。</td></tr>'
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>成员管理</h2>
              <div class="subtle">课题组成员与角色档案。</div>
            </div>
            <div class="button-row">
              <a class="button primary" href="/members/add">添加成员</a>
            </div>
          </div>
          <article class="card">
            <table class="table">
              <thead><tr><th>编号</th><th>姓名</th><th>角色</th><th>邮箱</th><th>操作</th></tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </article>
        </section>
        """
        return self.render_layout("成员管理", body, active_section="members", current_user=current_user)

    def render_pending_accounts_page(self, current_user: WebUser, notice: str = "") -> str:
        if current_user.role not in {Role.ADMIN, Role.PI}:
            body = """
            <section class="stack">
              <div class="topbar"><div><h2>账号审核</h2><div class="subtle">只有管理员和 PI 可以审核注册申请。</div></div></div>
              <div class="empty-state">当前账号没有审核权限。</div>
            </section>
            """
            return self.render_layout("账号审核", body, active_section="accounts", current_user=current_user, notice=notice)

        pending_users = self.auth_store.list_pending_users()
        rows = "".join(
            f"<tr>"
            f"<td>{html.escape(user.display_name)}</td>"
            f"<td>{html.escape(user.username)}</td>"
            f"<td>{html.escape(user.created_at or '-')}</td>"
            f"<td><form method=\"post\" action=\"/accounts/{html.escape(quote(user.username, safe=''))}/approve\" style=\"display:inline-block;\">"
            f"<button class=\"button primary\" type=\"submit\">通过</button></form></td>"
            f"</tr>"
            for user in pending_users
        )
        table = (
            f"""
            <table class="table">
              <thead><tr><th>姓名</th><th>账号</th><th>注册时间</th><th>操作</th></tr></thead>
              <tbody>{rows}</tbody>
            </table>
            """
            if rows
            else '<div class="empty-state">暂无待审核账号。</div>'
        )
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>账号审核</h2>
              <div class="subtle">审核通过后，注册者可用姓名和密码登录。</div>
            </div>
          </div>
          <article class="card">{table}</article>
        </section>
        """
        return self.render_layout("账号审核", body, active_section="accounts", current_user=current_user, notice=notice)

    def render_review_workbench(self, current_user: WebUser, notice: str = "") -> str:
        if current_user.role not in {Role.ADMIN, Role.PI}:
            body = """
            <section class="stack">
              <div class="topbar"><div><h2>审核工作台</h2><div class="subtle">只有管理员和 PI 可以审核成果。</div></div></div>
              <div class="empty-state">当前账号没有审核权限。</div>
            </section>
            """
            return self.render_layout("审核工作台", body, active_section="reviews", current_user=current_user, notice=notice)

        pending_outputs = self.repository.list_outputs(status=ReviewStatus.SUBMITTED)
        rows = "".join(
            f"<tr>"
            f"<td><a href=\"/outputs/{html.escape(output.output_id)}\">{html.escape(output.output_id)}</a></td>"
            f"<td>{html.escape(output.title)}</td>"
            f"<td>{html.escape(output_type_label(output.output_type))}</td>"
            f"<td>{self._status_badge(output.review_status)}</td>"
            f"<td>"
            f"<form method=\"post\" action=\"/outputs/{html.escape(output.output_id)}/approve\" style=\"display:inline-block;margin-right:8px;\"><input type=\"hidden\" name=\"comment\" value=\"通过Web审核\" /><input type=\"hidden\" name=\"next\" value=\"/reviews\" /><button class=\"button primary\" type=\"submit\">通过</button></form>"
            f"<form method=\"post\" action=\"/outputs/{html.escape(output.output_id)}/return\" style=\"display:inline-block;\"><input type=\"hidden\" name=\"comment\" value=\"退回补充材料\" /><input type=\"hidden\" name=\"next\" value=\"/reviews\" /><button class=\"button secondary\" type=\"submit\">退回</button></form>"
            f"</td>"
            f"</tr>"
            for output in pending_outputs
        )
        table = (
            f"""
            <table class="table">
              <thead><tr><th>编号</th><th>标题</th><th>类型</th><th>状态</th><th>操作</th></tr></thead>
              <tbody>{rows}</tbody>
            </table>
            """
            if rows
            else '<div class="empty-state">暂无待审核成果。</div>'
        )
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>审核工作台</h2>
              <div class="subtle">集中处理已提交成果。</div>
            </div>
            <div class="button-row">
              <a class="button secondary" href="/outputs">全部成果</a>
            </div>
          </div>
          <article class="card">{table}</article>
        </section>
        """
        return self.render_layout("审核工作台", body, active_section="reviews", current_user=current_user, notice=notice)

    def render_projects_page(self, current_user: WebUser) -> str:
        projects = self.repository.list_projects()
        rows = "".join(
            f"<tr>"
            f"<td><a href=\"/projects/{html.escape(project.project_id)}\">{html.escape(project.project_id)}</a></td>"
            f"<td>{html.escape(project.name)}</td>"
            f"<td>{html.escape(project.project_type)}</td>"
            f"<td>{html.escape(', '.join(project.owner_member_ids) or '-')}</td>"
            f"</tr>"
            for project in projects
        ) or '<tr><td colspan="4" class="muted">暂无项目数据。</td></tr>'
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>项目管理</h2>
              <div class="subtle">课题、基金与合作项目。</div>
            </div>
            <div class="button-row">
              <a class="button primary" href="/projects/add">添加项目</a>
            </div>
          </div>
          <article class="card">
            <table class="table">
              <thead><tr><th>编号</th><th>名称</th><th>类型</th><th>负责人</th></tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </article>
        </section>
        """
        return self.render_layout("项目管理", body, active_section="projects", current_user=current_user)

    def render_outputs_page(self, current_user: WebUser) -> str:
        outputs = self.repository.list_outputs_for_actor(current_user.role, current_user.member_id)
        rows = "".join(
            f"<tr>"
            f"<td><a href=\"/outputs/{html.escape(output.output_id)}\">{html.escape(output.output_id)}</a></td>"
            f"<td>{html.escape(output.title)}</td>"
            f"<td>{html.escape(output_type_label(output.output_type))}</td>"
            f"<td>{self._status_badge(output.review_status)}</td>"
            f"<td>{html.escape(str(output.year) if output.year is not None else '-')}</td>"
            f"</tr>"
            for output in outputs
        ) or '<tr><td colspan="5" class="muted">暂无成果数据。</td></tr>'
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>成果管理</h2>
              <div class="subtle">成果记录、状态和项目关联。</div>
            </div>
            <div class="button-row">
              <a class="button primary" href="/outputs/add">添加成果</a>
            </div>
          </div>
          <article class="card">
            <table class="table">
              <thead><tr><th>编号</th><th>标题</th><th>类型</th><th>状态</th><th>年份</th></tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </article>
        </section>
        """
        return self.render_layout("成果管理", body, active_section="outputs", current_user=current_user)

    def render_import_page(self, current_user: WebUser, error: str = "") -> str:
        error_html = f'<div class="notice">{html.escape(error)}</div>' if error else ""
        members = self.repository.list_members()
        owner_options = "".join(
            f'<label style="display:flex;gap:8px;padding:8px;"><input type="checkbox" name="owner_member_ids" value="{html.escape(m.member_id)}"{" checked" if m.member_id == current_user.member_id else ""} /><span>{html.escape(m.name)} ({html.escape(m.member_id)})</span></label>'
            for m in members
        )
        body = f"""
        <section class="stack">
          <div class="section-banner">
            <h2>外部数据抓取</h2>
            <p>输入 DOI、PubMed ID 或专利号，自动预填成果字段。抓取失败时仍可手动继续编辑。</p>
          </div>
          {error_html}
          <div class="workflow-grid">
            <article class="workflow-card"><strong>DOI / CrossRef</strong><span>自动填充标题、作者、期刊、年份和摘要。</span></article>
            <article class="workflow-card"><strong>PubMed / E-utilities</strong><span>适合医学文献，可自动抓取 PMID 对应的文章元数据。</span></article>
            <article class="workflow-card"><strong>专利 / 公开数据源</strong><span>按专利号或申请号检索，预填专利标题、申请信息和权利人。</span></article>
          </div>
          <div class="detail-grid">
            <article class="card">
              <form method="post" action="/import/fetch" class="stack">
                <div class="form-grid">
                  <div class="field span-2">
                    <label for="source_type">抓取类型</label>
                    <select id="source_type" name="source_type" required style="width:100%;padding:12px 14px;border-radius:14px;border:1px solid var(--line);">
                      <option value="doi">DOI / CrossRef</option>
                      <option value="pmid">PubMed / PMID</option>
                      <option value="patent">专利号 / 申请号</option>
                    </select>
                  </div>
                  <div class="field span-2">
                    <label for="query">检索值</label>
                    <input id="query" name="query" required value="10.3390/biom12060824" placeholder="例如 10.3390/biom12060824、38902948 或 CN202410000000.0" />
                    <div class="inline-help">抓取后会直接进入成果详情页，供你继续补全和核对字段。</div>
                  </div>
                  <div class="field span-2">
                    <label for="title">成果标题（可选）</label>
                    <input id="title" name="title" placeholder="不填则使用抓取到的标题" />
                  </div>
                  <div class="field">
                    <label for="output_id">成果编号</label>
                    <input id="output_id" name="output_id" placeholder="不填则自动生成" />
                  </div>
                  <div class="field span-2">
                    <label>负责人</label>
                    <div style="border:1px solid var(--line);border-radius:14px;padding:8px;max-height:200px;overflow-y:auto;">
                      {owner_options if owner_options else '<p class="muted">暂无成员。</p>'}
                    </div>
                    <input id="owner_member_ids_manual" name="owner_member_ids_manual" placeholder="手动输入负责人，多个用逗号、分号或换行分隔" style="margin-top:10px;" />
                  </div>
                </div>
                <div class="button-row">
                  <button class="button primary" type="submit">抓取并预填</button>
                  <a class="button secondary" href="/outputs/add">直接手动录入</a>
                </div>
              </form>
            </article>
            <article class="card">
              <form method="post" action="/import/upload" enctype="multipart/form-data" class="stack">
                <div class="section-banner" style="margin-bottom: 0;">
                  <h3>上传文档识别</h3>
                  <p>上传论文 PDF、Word 或纯文本，系统会尝试自动识别题名、年份、摘要、DOI / PMID / 专利号，并预填到成果表单。</p>
                </div>
                <div class="field">
                  <label for="document_file">选择文档</label>
                  <input id="document_file" name="document_file" type="file" accept=".pdf,.docx,.txt,.html,.htm,.xml" required />
                  <div class="inline-help">建议上传可复制文本的版本，扫描件图片目前无法稳定识别。</div>
                </div>
                <div class="button-row">
                  <button class="button primary" type="submit">上传并识别</button>
                </div>
              </form>
            </article>
          </div>
        </section>
        """
        return self.render_layout("外部数据抓取", body, active_section="outputs", current_user=current_user)

    def render_output_detail(self, current_user: WebUser, output: ResearchOutput, notice: str = "") -> str:
        actions = []
        if can_perform(current_user.role, Permission.EDIT, output=output, actor_member_id=current_user.member_id):
            actions.append(
                f'<a class="button secondary" href="/outputs/{html.escape(output.output_id)}/edit">编辑</a>'
            )
            actions.append(
                f'<form method="post" action="/outputs/{html.escape(output.output_id)}/submit" style="display:inline-block;"><button class="button primary" type="submit">提交审核</button></form>'
            )
        if can_perform(current_user.role, Permission.REVIEW, output=output, actor_member_id=current_user.member_id):
            actions.append(
                f'<form method="post" action="/outputs/{html.escape(output.output_id)}/approve" style="display:inline-block;"><input type="hidden" name="comment" value="通过Web界面审核通过" /><button class="button secondary" type="submit">通过审核</button></form>'
            )
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>{html.escape(output.title)}</h2>
              <div class="subtle">{html.escape(output.output_id)} · {html.escape(output_type_label(output.output_type))}</div>
            </div>
            <div class="button-row">{''.join(actions)}</div>
          </div>
          <div class="detail-grid">
            <article class="card">
              <div class="panel-title">
                <h3>概览</h3>
                <span>{self._status_badge(output.review_status)}</span>
              </div>
              <div class="kv">
                <div><span>状态</span><span>{html.escape(review_status_label(output.review_status))}</span></div>
                <div><span>年份</span><span>{html.escape(str(output.year) if output.year is not None else '-')}</span></div>
                <div><span>负责人</span><span>{html.escape(', '.join(output.owner_member_ids))}</span></div>
                <div><span>参与人</span><span>{html.escape(', '.join(output.participant_member_ids) or '-')}</span></div>
                <div><span>关联项目</span><span>{html.escape(', '.join(output.project_ids) or '-')}</span></div>
                <div><span>关键词</span><span>{html.escape(', '.join(output.keywords) or '-')}</span></div>
              </div>
            </article>
            <article class="card">
              <div class="panel-title">
                <h3>元数据</h3>
                <span>结构化字段</span>
              </div>
              {self._detail_metadata(output)}
            </article>
          </div>
          <article class="card">
            <div class="panel-title">
              <h3>备注</h3>
              <span>摘要与评论</span>
            </div>
            <p class="muted">{html.escape(output.summary or '暂无摘要。')}</p>
            <p class="muted">{html.escape(output.notes or '暂无备注。')}</p>
          </article>
        </section>
        """
        return self.render_layout(
            output.output_id,
            body,
            active_section="outputs",
            current_user=current_user,
            notice=notice,
        )

    def render_setup_or_login(self) -> Tuple[str, str]:
        if self.auth_store.has_users():
            return "login", self.render_login_page()
        return "setup", self.render_setup_page()

    def _normalise_output_id(self, value: str, source_type: str, *, year: Optional[int] = None) -> str:
        trimmed = value.strip()
        if trimmed:
            return trimmed
        output_type = OutputType.PATENT if source_type == "patent" else OutputType.ARTICLE
        return self.repository.generate_output_id(output_type, year=year)

    def _merge_people_fields(
        self,
        fields_multi: Dict[str, List[str]],
        checkbox_name: str,
        manual_name: str,
    ) -> List[str]:
        values = [v.strip() for v in fields_multi.get(checkbox_name, []) if v.strip()]
        raw_manual = fields_multi.get(manual_name, [""])[0]
        for separator in (";", "；", "，", "\n", "\r"):
            raw_manual = raw_manual.replace(separator, ",")
        values.extend(item.strip() for item in raw_manual.split(",") if item.strip())
        merged: List[str] = []
        seen = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            merged.append(value)
        return merged

    def _resolve_owner_ids_from_fields(
        self,
        fields: Dict[str, str],
        current_user: WebUser,
        fields_multi: Optional[Dict[str, List[str]]] = None,
    ) -> List[str]:
        owner_ids: List[str]
        if fields_multi is None:
            owner_ids = []
        else:
            owner_ids = self._merge_people_fields(fields_multi, "owner_member_ids", "owner_member_ids_manual")
        legacy_owner = fields.get("owner_member_id", "").strip()
        if legacy_owner:
            owner_ids.append(legacy_owner)
        if not owner_ids:
            owner_ids.append(current_user.member_id)
        merged: List[str] = []
        seen = set()
        for owner_id in owner_ids:
            if owner_id in seen:
                continue
            seen.add(owner_id)
            merged.append(owner_id)
        return merged

    def _build_output_from_fetch(
        self,
        fields: Dict[str, str],
        current_user: WebUser,
        fields_multi: Optional[Dict[str, List[str]]] = None,
    ) -> ResearchOutput:
        source_type = fields.get("source_type", "").strip()
        query = fields.get("query", "").strip()
        owner_ids = self._resolve_owner_ids_from_fields(fields, current_user, fields_multi)
        if source_type == "doi":
            article_data = fetch_article_metadata(doi=query)
            if article_data is None:
                raise ValueError("未能通过 DOI 抓取到文章信息。")
            article = ArticleMetadata(
                article_type="research_article",
                journal=article_data.journal or "",
                doi=article_data.doi or query,
                pmid=article_data.pmid or "",
                publication_year=article_data.year,
                first_authors=article_data.authors[:3],
            )
            return ResearchOutput(
                output_id=self._normalise_output_id(fields.get("output_id", ""), source_type, year=article_data.year),
                title=fields.get("title", "").strip() or article_data.title or query,
                output_type=OutputType.ARTICLE,
                owner_member_ids=owner_ids,
                year=article_data.year,
                summary=article_data.abstract or "",
                article=article,
            )
        if source_type == "pmid":
            article_data = fetch_article_metadata(pmid=query)
            if article_data is None:
                raise ValueError("未能通过 PubMed PMID 抓取到文章信息。")
            article = ArticleMetadata(
                article_type="research_article",
                journal=article_data.journal or "",
                doi=article_data.doi or "",
                pmid=article_data.pmid or query,
                publication_year=article_data.year,
                first_authors=article_data.authors[:3],
            )
            return ResearchOutput(
                output_id=self._normalise_output_id(fields.get("output_id", ""), source_type, year=article_data.year),
                title=fields.get("title", "").strip() or article_data.title or query,
                output_type=OutputType.ARTICLE,
                owner_member_ids=owner_ids,
                year=article_data.year,
                summary=article_data.abstract or "",
                article=article,
            )
        if source_type == "patent":
            patent_data = self._fetch_patent_metadata(query)
            if patent_data is None:
                raise ValueError("未能通过专利号抓取到专利信息。")
            patent = PatentMetadata(
                patent_number=patent_data.patent_number,
                application_number=patent_data.application_number,
                title=patent_data.title,
                country_code=patent_data.country_code,
                kind_code=patent_data.kind_code,
                inventors=patent_data.inventors,
                assignees=patent_data.applicants,
                application_date=patent_data.filing_date or "",
                publication_date=patent_data.publication_date or "",
                status=patent_data.status or "",
                abstract=patent_data.abstract or "",
                url=patent_data.url or "",
            )
            return ResearchOutput(
                output_id=self._normalise_output_id(fields.get("output_id", ""), source_type),
                title=fields.get("title", "").strip() or patent.title or query,
                output_type=OutputType.PATENT,
                owner_member_ids=owner_ids,
                summary=patent.abstract,
                patent=patent,
            )
        raise ValueError("请选择有效的抓取类型。")

    def _build_output_from_document_draft(self, draft: DocumentImportDraft, current_user: WebUser) -> ResearchOutput:
        owner_ids = [current_user.member_id]
        if draft.output_type == "patent":
            patent_data = draft.patent
            if patent_data is None:
                raise ValueError("文档识别结果缺少专利信息。")
            patent = PatentMetadata(
                patent_number=patent_data.patent_number,
                application_number=patent_data.application_number,
                title=patent_data.title,
                country_code=patent_data.country_code,
                kind_code=patent_data.kind_code,
                inventors=patent_data.inventors,
                assignees=patent_data.applicants,
                application_date=patent_data.filing_date or "",
                publication_date=patent_data.publication_date or "",
                status=patent_data.status or "",
                abstract=patent_data.abstract or "",
                url=patent_data.url or "",
            )
            return ResearchOutput(
                output_id=self.repository.generate_output_id(OutputType.PATENT, year=draft.year),
                title=draft.title,
                output_type=OutputType.PATENT,
                owner_member_ids=owner_ids,
                year=draft.year,
                summary=draft.summary,
                patent=patent,
            )
        article_data = draft.article
        if article_data is None:
            raise ValueError("文档识别结果缺少文章信息。")
        article = ArticleMetadata(
            article_type="research_article",
            journal=article_data.journal or "",
            doi=article_data.doi or "",
            pmid=article_data.pmid or "",
            publication_year=article_data.year,
            first_authors=article_data.authors[:3],
        )
        return ResearchOutput(
            output_id=self.repository.generate_output_id(OutputType.ARTICLE, year=draft.year or article_data.year),
            title=draft.title,
            output_type=OutputType.ARTICLE,
            owner_member_ids=owner_ids,
            year=draft.year or article_data.year,
            summary=draft.summary,
            article=article,
        )

    def _fetch_patent_metadata(self, query: str) -> Optional[object]:
        from .data_fetcher import DataFetcher

        fetcher = DataFetcher()
        return fetcher.fetch_patent_by_number(query)

    def _apply_fetched_output(self, output: ResearchOutput) -> ResearchOutput:
        return output

    def _metric_card(self, label: str, value: str, hint: str) -> str:
        return f"""
        <article class="card">
          <div class="metric-label">{html.escape(label)}</div>
          <div class="metric-value">{html.escape(value)}</div>
          <div class="metric-hint">{html.escape(hint)}</div>
        </article>
        """

    def _export_button(self, current_user: WebUser) -> str:
        if not can_perform(current_user.role, Permission.EXPORT, actor_member_id=current_user.member_id):
            return ""
        return '<a class="button secondary" href="/export/excel">导出Excel</a>'

    def _count_labels(self, labels: Iterable[str]) -> Dict[str, int]:
        return dict(sorted(Counter(labels).items()))

    def _bar_chart(self, counts: Dict[str, int], *, accent_class: str) -> str:
        if not counts:
            return '<div class="muted">暂无数据。</div>'
        maximum = max(counts.values()) or 1
        rows = []
        for label, value in counts.items():
            width = max(8, round((value / maximum) * 100))
            classes = "bar-fill"
            if accent_class:
                classes = f"bar-fill {accent_class}"
            rows.append(
                f'<div class="bar-row"><div>{html.escape(label)}</div><div class="bar-track"><div class="{classes}" style="width:{width}%"></div></div><div>{value}</div></div>'
            )
        return f'<div class="bar-chart">{"".join(rows)}</div>'

    def _output_table(self, outputs: List[ResearchOutput]) -> str:
        rows = "".join(
            f"<tr><td><a href=\"/outputs/{html.escape(output.output_id)}\">{html.escape(output.output_id)}</a></td><td>{html.escape(output.title)}</td><td>{html.escape(output_type_label(output.output_type))}</td><td>{self._status_badge(output.review_status)}</td></tr>"
            for output in outputs
        ) or '<tr><td colspan="4" class="muted">暂无成果数据。</td></tr>'
        return f"""
        <table class="table">
          <thead><tr><th>编号</th><th>标题</th><th>类型</th><th>状态</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
        """

    def _status_badge(self, status: ReviewStatus) -> str:
        return f'<span class="badge status-{html.escape(status.value)}">{html.escape(review_status_label(status))}</span>'

    def _detail_metadata(self, output: ResearchOutput) -> str:
        chunks = [
            f"<div class='kv'><div><span>创建时间</span><span>{html.escape(output.created_at)}</span></div><div><span>更新时间</span><span>{html.escape(output.updated_at)}</span></div></div>"
        ]
        if output.article:
            chunks.append(
                f"""
                <div class="kv">
                  <div><span>文章类型</span><span>{html.escape(output.article.article_type)}</span></div>
                  <div><span>期刊</span><span>{html.escape(output.article.journal or '-')}</span></div>
                  <div><span>DOI</span><span>{html.escape(output.article.doi or '-')}</span></div>
                  <div><span>投稿状态</span><span>{html.escape(output.article.submission_status or '-')}</span></div>
                </div>
                """
            )
        if output.patent:
            chunks.append(
                f"""
                <div class="kv">
                  <div><span>专利号</span><span>{html.escape(output.patent.patent_number or '-')}</span></div>
                  <div><span>申请号</span><span>{html.escape(output.patent.application_number or '-')}</span></div>
                  <div><span>国家/地区</span><span>{html.escape(output.patent.country_code or '-')}</span></div>
                  <div><span>状态</span><span>{html.escape(output.patent.status or '-')}</span></div>
                </div>
                """
            )
        return "".join(chunks)

    def render_member_form(
        self, current_user: WebUser, member: Optional[Member] = None, error: str = ""
    ) -> str:
        is_edit = member is not None
        title = "编辑成员" if is_edit else "添加成员"
        action = f"/members/{html.escape(member.member_id)}/edit" if is_edit else "/members/add"
        member_id_field = (
            f'<input id="member_id" name="member_id" value="{html.escape(member.member_id)}" readonly />'
            if is_edit
            else '<input id="member_id" name="member_id" required />'
        )
        error_html = f'<div class="notice">{html.escape(error)}</div>' if error else ""
        role_options = "".join(
            f'<option value="{role.value}"{" selected" if member and member.role == role else ""}>{html.escape(role_label(role))}</option>'
            for role in Role
        )
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>{title}</h2>
              <div class="subtle">{'修改成员信息' if is_edit else '添加新成员到课题组'}</div>
            </div>
          </div>
          <article class="card">
            {error_html}
            <form method="post" action="{action}" class="stack">
              <div class="field">
                <label for="member_id">成员编号 *</label>
                {member_id_field}
              </div>
              <div class="field">
                <label for="name">姓名 *</label>
                <input id="name" name="name" value="{html.escape(member.name) if member else ''}" required />
              </div>
              <div class="field">
                <label for="role">角色 *</label>
                <select id="role" name="role" required style="width:100%;padding:12px 14px;border-radius:14px;border:1px solid var(--line);">{role_options}</select>
              </div>
              <div class="field">
                <label for="email">邮箱</label>
                <input id="email" name="email" type="email" value="{html.escape(member.email) if member else ''}" />
              </div>
              <div class="field">
                <label for="notes">备注</label>
                <textarea id="notes" name="notes" rows="3" style="width:100%;resize:vertical;">{html.escape(member.notes) if member else ''}</textarea>
              </div>
              <div class="button-row">
                <button class="button primary" type="submit">{'保存' if is_edit else '添加'}</button>
                <a class="button secondary" href="/members">取消</a>
              </div>
            </form>
          </article>
        </section>
        """
        return self.render_layout(title, body, active_section="members", current_user=current_user)

    def render_member_detail(self, current_user: WebUser, member: Member, notice: str = "") -> str:
        promote_button = ""
        if current_user.role in {Role.ADMIN, Role.PI} and member.role != Role.ADMIN:
            promote_button = (
                f'<form method="post" action="/members/{html.escape(member.member_id)}/promote" style="display:inline-block;"><button class="button secondary" type="submit">设为管理员</button></form>'
            )
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>{html.escape(member.name)}</h2>
              <div class="subtle">{html.escape(member.member_id)} · {html.escape(role_label(member.role))}</div>
            </div>
            <div class="button-row">
              <a class="button primary" href="/members/{html.escape(member.member_id)}/edit">编辑</a>
              {promote_button}
              <form method="post" action="/members/{html.escape(member.member_id)}/delete" style="display:inline-block;" onsubmit="return confirm('确认删除成员 {html.escape(member.name)}？此操作不可恢复。');">
                <button class="button secondary" type="submit">删除</button>
              </form>
            </div>
          </div>
          <article class="card">
            <div class="kv">
              <div><span>成员编号</span><span>{html.escape(member.member_id)}</span></div>
              <div><span>姓名</span><span>{html.escape(member.name)}</span></div>
              <div><span>角色</span><span>{html.escape(role_label(member.role))}</span></div>
              <div><span>邮箱</span><span>{html.escape(member.email or '-')}</span></div>
              <div><span>备注</span><span>{html.escape(member.notes or '-')}</span></div>
            </div>
          </article>
        </section>
        """
        return self.render_layout(member.name, body, active_section="members", current_user=current_user, notice=notice)

    def render_project_form(
        self, current_user: WebUser, project: Optional[Project] = None, error: str = ""
    ) -> str:
        is_edit = project is not None
        title = "编辑项目" if is_edit else "添加项目"
        action = f"/projects/{html.escape(project.project_id)}/edit" if is_edit else "/projects/add"
        project_id_field = (
            f'<input id="project_id" name="project_id" value="{html.escape(project.project_id)}" readonly />'
            if is_edit
            else '<input id="project_id" name="project_id" required />'
        )
        error_html = f'<div class="notice">{html.escape(error)}</div>' if error else ""
        members = self.repository.list_members()
        member_checkboxes = "".join(
            f'<label style="display:flex;gap:8px;padding:8px;"><input type="checkbox" name="owner_member_ids" value="{html.escape(m.member_id)}"{" checked" if project and m.member_id in project.owner_member_ids else ""} /><span>{html.escape(m.name)} ({html.escape(m.member_id)})</span></label>'
            for m in members
        )
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>{title}</h2>
              <div class="subtle">{'修改项目信息' if is_edit else '添加新项目或课题'}</div>
            </div>
          </div>
          <article class="card">
            {error_html}
            <form method="post" action="{action}" class="stack">
              <div class="field">
                <label for="project_id">项目编号 *</label>
                {project_id_field}
              </div>
              <div class="field">
                <label for="name">项目名称 *</label>
                <input id="name" name="name" value="{html.escape(project.name) if project else ''}" required />
              </div>
              <div class="field">
                <label for="project_type">项目类型 *</label>
                <input id="project_type" name="project_type" value="{html.escape(project.project_type) if project else ''}" required placeholder="如：国家自然科学基金、省级课题等" />
              </div>
              <div class="field">
                <label>负责人 *</label>
                <div style="border:1px solid var(--line);border-radius:14px;padding:8px;max-height:200px;overflow-y:auto;">
                  {member_checkboxes if member_checkboxes else '<p class="muted">暂无成员，请先添加成员。</p>'}
                </div>
                <div class="inline-help">可勾选成员，也可在下方手动输入未建档负责人。</div>
                <input id="owner_member_ids_manual" name="owner_member_ids_manual" placeholder="手动输入负责人，多个用逗号、分号或换行分隔" style="margin-top:10px;" />
              </div>
              <div class="field">
                <label for="funding_source">资助来源</label>
                <input id="funding_source" name="funding_source" value="{html.escape(project.funding_source) if project else ''}" />
              </div>
              <div class="field">
                <label for="start_year">开始年份</label>
                <input id="start_year" name="start_year" type="number" min="1900" max="2100" value="{project.start_year if project and project.start_year else ''}" />
              </div>
              <div class="field">
                <label for="end_year">结束年份</label>
                <input id="end_year" name="end_year" type="number" min="1900" max="2100" value="{project.end_year if project and project.end_year else ''}" />
              </div>
              <div class="button-row">
                <button class="button primary" type="submit">{'保存' if is_edit else '添加'}</button>
                <a class="button secondary" href="/projects">取消</a>
              </div>
            </form>
          </article>
        </section>
        """
        return self.render_layout(title, body, active_section="projects", current_user=current_user)

    def render_project_detail(self, current_user: WebUser, project: Project, notice: str = "") -> str:
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>{html.escape(project.name)}</h2>
              <div class="subtle">{html.escape(project.project_id)} · {html.escape(project.project_type)}</div>
            </div>
            <div class="button-row">
              <a class="button primary" href="/projects/{html.escape(project.project_id)}/edit">编辑</a>
              <form method="post" action="/projects/{html.escape(project.project_id)}/delete" style="display:inline-block;" onsubmit="return confirm('确认删除项目 {html.escape(project.name)}？此操作不可恢复。');">
                <button class="button secondary" type="submit">删除</button>
              </form>
            </div>
          </div>
          <article class="card">
            <div class="kv">
              <div><span>项目编号</span><span>{html.escape(project.project_id)}</span></div>
              <div><span>项目名称</span><span>{html.escape(project.name)}</span></div>
              <div><span>项目类型</span><span>{html.escape(project.project_type)}</span></div>
              <div><span>负责人</span><span>{html.escape(', '.join(project.owner_member_ids) or '-')}</span></div>
              <div><span>资助来源</span><span>{html.escape(project.funding_source or '-')}</span></div>
              <div><span>开始年份</span><span>{html.escape(str(project.start_year) if project.start_year else '-')}</span></div>
              <div><span>结束年份</span><span>{html.escape(str(project.end_year) if project.end_year else '-')}</span></div>
            </div>
          </article>
        </section>
        """
        return self.render_layout(project.name, body, active_section="projects", current_user=current_user, notice=notice)

    def render_output_form(
        self,
        current_user: WebUser,
        output: Optional[ResearchOutput] = None,
        error: str = "",
        *,
        notice: str = "",
        form_action: Optional[str] = None,
        form_title: Optional[str] = None,
        submit_label: Optional[str] = None,
        prefill_mode: bool = False,
    ) -> str:
        is_edit = output is not None and not prefill_mode
        title = form_title or ("编辑成果" if is_edit else "添加成果")
        action = form_action or (f"/outputs/{html.escape(output.output_id)}/edit" if is_edit else "/outputs/add")
        output_id_field = (
            f'<input id="output_id" name="output_id" value="{html.escape(output.output_id)}" readonly />'
            if is_edit
            else (
                f'<input id="output_id" name="output_id" value="{html.escape(output.output_id)}" placeholder="留空自动按类别生成，如 LW-2026-001" />'
                if output and prefill_mode and output.output_id
                else '<input id="output_id" name="output_id" placeholder="留空自动按类别生成，如 LW-2026-001" />'
            )
        )
        error_html = f'<div class="notice">{html.escape(error)}</div>' if error else ""
        notice_html = f'<div class="notice">{html.escape(notice)}</div>' if notice else ""
        output_type_options = "".join(
            f'<option value="{ot.value}"{" selected" if output and output.output_type == ot else ""}>{html.escape(output_type_label(ot))}</option>'
            for ot in OutputType
        )
        members = self.repository.list_members()
        owner_checkboxes = "".join(
            f'<label style="display:flex;gap:8px;padding:8px;"><input type="checkbox" name="owner_member_ids" value="{html.escape(m.member_id)}"{" checked" if output and m.member_id in output.owner_member_ids else ""} /><span>{html.escape(m.name)} ({html.escape(m.member_id)})</span></label>'
            for m in members
        )
        participant_checkboxes = "".join(
            f'<label style="display:flex;gap:8px;padding:8px;"><input type="checkbox" name="participant_member_ids" value="{html.escape(m.member_id)}"{" checked" if output and m.member_id in output.participant_member_ids else ""} /><span>{html.escape(m.name)} ({html.escape(m.member_id)})</span></label>'
            for m in members
        )
        projects = self.repository.list_projects()
        project_checkboxes = "".join(
            f'<label style="display:flex;gap:8px;padding:8px;"><input type="checkbox" name="project_ids" value="{html.escape(p.project_id)}"{" checked" if output and p.project_id in output.project_ids else ""} /><span>{html.escape(p.name)} ({html.escape(p.project_id)})</span></label>'
            for p in projects
        )
        article_display = 'style="display:block;"' if output and output.output_type == OutputType.ARTICLE else 'style="display:none;"'
        patent_display = 'style="display:block;"' if output and output.output_type == OutputType.PATENT else 'style="display:none;"'
        article = output.article if output and output.article else None
        patent = output.patent if output and output.patent else None
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>{title}</h2>
              <div class="subtle">{'修改成果信息' if is_edit else '添加新成果记录'}</div>
            </div>
            <div class="button-row">
              <a class="button ghost" href="/import">从 DOI / PubMed / 专利抓取</a>
            </div>
          </div>
          <article class="card">
            {notice_html}
            {error_html}
            <form method="post" action="{action}" class="stack">
              <div class="form-grid">
                <div class="field">
                  <label for="output_id">成果编号</label>
                  {output_id_field}
                  <div class="inline-help">留空时按成果类别和年份自动生成编号，例如论文 LW-2026-001、专利 ZL-2026-001。</div>
                </div>
                <div class="field">
                  <label for="title">成果标题 *</label>
                  <input id="title" name="title" value="{html.escape(output.title) if output else ''}" required />
                </div>
                <div class="field">
                  <label for="output_type">成果类型 *</label>
                  <select id="output_type" name="output_type" required style="width:100%;padding:12px 14px;border-radius:14px;border:1px solid var(--line);" onchange="toggleOutputFields(this.value)">{output_type_options}</select>
                </div>
                <div class="field">
                  <label for="year">年份</label>
                  <input id="year" name="year" type="number" min="1900" max="2100" value="{output.year if output and output.year else ''}" />
                </div>
                <div class="field span-2">
                  <label>负责人 *</label>
                  <div style="border:1px solid var(--line);border-radius:14px;padding:8px;max-height:200px;overflow-y:auto;">
                    {owner_checkboxes if owner_checkboxes else '<p class="muted">暂无成员。</p>'}
                  </div>
                  <div class="inline-help">可勾选成员，也可在下方手动输入未建档成员或外部合作者。</div>
                  <input id="owner_member_ids_manual" name="owner_member_ids_manual" placeholder="手动输入负责人，多个用逗号、分号或换行分隔" style="margin-top:10px;" />
                </div>
                <div class="field span-2">
                  <label>参与人</label>
                  <div style="border:1px solid var(--line);border-radius:14px;padding:8px;max-height:200px;overflow-y:auto;">
                    {participant_checkboxes if participant_checkboxes else '<p class="muted">暂无成员。</p>'}
                  </div>
                  <input id="participant_member_ids_manual" name="participant_member_ids_manual" placeholder="手动输入参与人，多个用逗号、分号或换行分隔" style="margin-top:10px;" />
                </div>
                <div class="field span-2">
                  <label>关联项目</label>
                  <div style="border:1px solid var(--line);border-radius:14px;padding:8px;max-height:200px;overflow-y:auto;">
                    {project_checkboxes if project_checkboxes else '<p class="muted">暂无项目。</p>'}
                  </div>
                </div>
                <div class="field span-2">
                  <label for="keywords">关键词（逗号分隔）</label>
                  <input id="keywords" name="keywords" value="{html.escape(', '.join(output.keywords)) if output else ''}" placeholder="keyword1, keyword2, keyword3" />
                </div>
                <div class="field span-2">
                  <label for="summary">摘要</label>
                  <textarea id="summary" name="summary" rows="4" style="width:100%;resize:vertical;">{html.escape(output.summary) if output else ''}</textarea>
                </div>
                <div class="field span-2">
                  <label for="notes">备注</label>
                  <textarea id="notes" name="notes" rows="3" style="width:100%;resize:vertical;">{html.escape(output.notes) if output else ''}</textarea>
                </div>
              </div>

              <div id="article-fields" {article_display} class="source-card">
                <h3>文章专属字段</h3>
                <div class="form-grid">
                  <div class="field">
                    <label for="article_type">文章类型 *</label>
                    <input id="article_type" name="article_type" value="{html.escape(article.article_type) if article else ''}" placeholder="如：Original Article, Review等" />
                  </div>
                  <div class="field">
                    <label for="journal">期刊</label>
                    <input id="journal" name="journal" value="{html.escape(article.journal) if article else ''}" />
                  </div>
                  <div class="field">
                    <label for="doi">DOI</label>
                    <input id="doi" name="doi" value="{html.escape(article.doi) if article else ''}" />
                  </div>
                  <div class="field">
                    <label for="pmid">PMID</label>
                    <input id="pmid" name="pmid" value="{html.escape(article.pmid) if article else ''}" />
                  </div>
                  <div class="field">
                    <label for="issn">ISSN</label>
                    <input id="issn" name="issn" value="{html.escape(article.issn) if article else ''}" />
                  </div>
                  <div class="field">
                    <label for="submission_status">投稿状态</label>
                    <input id="submission_status" name="submission_status" value="{html.escape(article.submission_status) if article else ''}" placeholder="如：已发表、审稿中等" />
                  </div>
                </div>
              </div>

              <div id="patent-fields" {patent_display} class="source-card">
                <h3>专利专属字段</h3>
                <div class="form-grid">
                  <div class="field">
                    <label for="patent_number">专利号</label>
                    <input id="patent_number" name="patent_number" value="{html.escape(patent.patent_number) if patent else ''}" />
                  </div>
                  <div class="field">
                    <label for="application_number">申请号</label>
                    <input id="application_number" name="application_number" value="{html.escape(patent.application_number) if patent else ''}" />
                  </div>
                  <div class="field span-2">
                    <label for="patent_title">专利标题</label>
                    <input id="patent_title" name="patent_title" value="{html.escape(patent.title) if patent else ''}" />
                  </div>
                  <div class="field">
                    <label for="patent_country">国家/地区</label>
                    <input id="patent_country" name="patent_country" value="{html.escape(patent.country_code) if patent else ''}" />
                  </div>
                  <div class="field">
                    <label for="patent_kind">类型代码</label>
                    <input id="patent_kind" name="patent_kind" value="{html.escape(patent.kind_code) if patent else ''}" />
                  </div>
                  <div class="field span-2">
                    <label for="patent_status">专利状态</label>
                    <input id="patent_status" name="patent_status" value="{html.escape(patent.status) if patent else ''}" />
                  </div>
                </div>
              </div>

              <div class="button-row">
                <button class="button secondary" type="submit" formaction="{'/outputs/' + html.escape(output.output_id) + '/save' if is_edit else '/outputs/save'}" formnovalidate>保存草稿</button>
                <button class="button primary" type="submit">{submit_label or ('提交修改' if is_edit else '提交审核')}</button>
                <a class="button secondary" href="/outputs">取消</a>
              </div>
            </form>
            <script>
              function toggleOutputFields(outputType) {{
                const articleFields = document.getElementById('article-fields');
                const patentFields = document.getElementById('patent-fields');
                const articleTypeInput = document.getElementById('article_type');
                if (outputType === 'article') {{
                  articleFields.style.display = 'block';
                  patentFields.style.display = 'none';
                  articleTypeInput.required = true;
                }} else if (outputType === 'patent') {{
                  articleFields.style.display = 'none';
                  patentFields.style.display = 'block';
                  articleTypeInput.required = false;
                }} else {{
                  articleFields.style.display = 'none';
                  patentFields.style.display = 'none';
                  articleTypeInput.required = false;
                }}
              }}
              toggleOutputFields(document.getElementById('output_type').value);
            </script>
          </article>
        </section>
        """
        return self.render_layout(title, body, active_section="outputs", current_user=current_user)


class LocalWebRequestHandler(BaseHTTPRequestHandler):
    server_version = "LitmanWeb/1.0"

    @property
    def app(self) -> WebApplication:
        return self.server.app  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        user = self.app.get_current_user(self)

        if path == "/":
            if not self.app.auth_store.has_users():
                self._send_html("Setup", self.app.render_setup_page())
                return
            if user is None:
                self.app.redirect(self, "/login")
                return
            self._send_html("Dashboard", self.app.render_dashboard(user))
            return
        if path == "/login":
            if not self.app.auth_store.has_users():
                self.app.redirect(self, "/setup")
                return
            if user is not None:
                self.app.redirect(self, "/")
                return
            self._send_html("Login", self.app.render_login_page())
            return
        if path == "/register":
            if not self.app.auth_store.has_users():
                self.app.redirect(self, "/setup")
                return
            if user is not None:
                self.app.redirect(self, "/")
                return
            self._send_html("Register", self.app.render_register_page())
            return
        if path == "/setup":
            if self.app.auth_store.has_users():
                self.app.redirect(self, "/login")
                return
            self._send_html("Setup", self.app.render_setup_page())
            return
        if path == "/logout":
            self._logout()
            return
        if user is None:
            self.app.redirect(self, "/login")
            return
        if path == "/export/excel":
            self._handle_excel_export(user)
            return
        is_admin_area = (
            path == "/members"
            or path.startswith("/members/")
            or path == "/projects"
            or path.startswith("/projects/")
            or path == "/accounts/pending"
            or path == "/reviews"
        )
        if is_admin_area and user.role not in {Role.ADMIN, Role.PI}:
            self.send_error(403, "Forbidden")
            return
        if path == "/members":
            self._send_html("Members", self.app.render_members_page(user))
            return
        if path == "/members/add":
            self._send_html("Add Member", self.app.render_member_form(user))
            return
        if path == "/accounts/pending":
            self._send_html("Pending Accounts", self.app.render_pending_accounts_page(user))
            return
        if path == "/reviews":
            self._send_html("Review Workbench", self.app.render_review_workbench(user))
            return
        if path.startswith("/members/") and path.endswith("/edit"):
            member_id = path[len("/members/") : -len("/edit")].strip("/")
            if not member_id or "/" in member_id:
                self.send_error(404, "Not Found")
                return
            try:
                member = self.app.repository.get_member(member_id)
            except KeyError:
                self.send_error(404, "Not Found")
                return
            self._send_html("Edit Member", self.app.render_member_form(user, member))
            return
        if path.startswith("/members/") and "/" not in path[len("/members/") :].strip("/"):
            member_id = path[len("/members/") :].strip("/")
            if not member_id:
                self.app.redirect(self, "/members")
                return
            try:
                member = self.app.repository.get_member(member_id)
            except KeyError:
                self.send_error(404, "Not Found")
                return
            self._send_html(member.name, self.app.render_member_detail(user, member))
            return
        if path == "/projects":
            self._send_html("Projects", self.app.render_projects_page(user))
            return
        if path == "/projects/add":
            self._send_html("Add Project", self.app.render_project_form(user))
            return
        if path.startswith("/projects/") and path.endswith("/edit"):
            project_id = path[len("/projects/") : -len("/edit")].strip("/")
            if not project_id or "/" in project_id:
                self.send_error(404, "Not Found")
                return
            try:
                project = self.app.repository.get_project(project_id)
            except KeyError:
                self.send_error(404, "Not Found")
                return
            self._send_html("Edit Project", self.app.render_project_form(user, project))
            return
        if path.startswith("/projects/") and "/" not in path[len("/projects/") :].strip("/"):
            project_id = path[len("/projects/") :].strip("/")
            if not project_id:
                self.app.redirect(self, "/projects")
                return
            try:
                project = self.app.repository.get_project(project_id)
            except KeyError:
                self.send_error(404, "Not Found")
                return
            self._send_html(project.name, self.app.render_project_detail(user, project))
            return
        if path == "/outputs":
            self._send_html("Outputs", self.app.render_outputs_page(user))
            return
        if path == "/import":
            self._send_html("Import", self.app.render_import_page(user))
            return
        if path == "/outputs/add":
            self._send_html("Add Output", self.app.render_output_form(user))
            return
        if path.startswith("/outputs/") and path.endswith("/edit"):
            output_id = path[len("/outputs/") : -len("/edit")].strip("/")
            if not output_id or "/" in output_id:
                self.send_error(404, "Not Found")
                return
            try:
                output = self.app.repository.get_output(output_id)
            except KeyError:
                self.send_error(404, "Not Found")
                return
            if not can_perform(user.role, Permission.VIEW, output=output, actor_member_id=user.member_id):
                self.send_error(403, "Forbidden")
                return
            self._send_html("Edit Output", self.app.render_output_form(user, output))
            return
        if path.startswith("/outputs/"):
            output_id = path[len("/outputs/") :].strip("/")
            if not output_id or "/" in output_id:
                self.send_error(404, "Not Found")
                return
            try:
                output = self.app.repository.get_output(output_id)
            except KeyError:
                self.send_error(404, "Not Found")
                return
            if not can_perform(user.role, Permission.VIEW, output=output, actor_member_id=user.member_id):
                self.send_error(403, "Forbidden")
                return
            self._send_html(output.title, self.app.render_output_detail(user, output))
            return
        self.send_error(404, "Not Found")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0") or "0")
        content_type = self.headers.get("Content-Type", "")
        is_multipart = "multipart/form-data" in content_type
        raw = ""
        parsed = {}
        if not is_multipart:
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            parsed = parse_qs(raw, keep_blank_values=True)
        fields = {key: values[0] if values else "" for key, values in parsed.items()}
        fields_multi = parsed  # Keep the full parsed data for multi-value fields

        if path == "/login":
            if not self.app.auth_store.has_users():
                self.app.redirect(self, "/setup")
                return
            username = fields.get("username", "")
            password = fields.get("password", "")
            captcha_token = fields.get("captcha_token", "")
            captcha_answer = fields.get("captcha_answer", "")
            if not self.app.login_captchas.verify(captcha_token, captcha_answer):
                self._send_html("登录", self.app.render_login_page("验证码错误。"), status=401)
                return
            user = self.app.auth_store.authenticate(username, password)
            if user is None:
                existing = self.app.auth_store.get_user(username)
                if existing is not None and existing.account_status == ACCOUNT_STATUS_PENDING:
                    self._send_html("登录", self.app.render_login_page("账号正在等待管理员审核。"), status=403)
                    return
                self._send_html("登录", self.app.render_login_page("姓名或密码错误。"), status=401)
                return
            token = self.app.sessions.create(user.username)
            self.send_response(303)
            self.app.set_session_cookie(self, token)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if path == "/setup":
            if self.app.auth_store.has_users():
                self.app.redirect(self, "/login")
                return
            try:
                workspace_name = fields.get("workspace_name", "").strip() or DEFAULT_WORKSPACE_NAME
                workspace_subtitle = fields.get("workspace_subtitle", "").strip() or "成果管理与审核工作台"
                self.app.save_settings(
                    WorkspaceSettings(workspace_name=workspace_name, workspace_subtitle=workspace_subtitle)
                )
                self.app.auth_store.create_user(
                    fields.get("username", ""),
                    fields.get("password", ""),
                    display_name=fields.get("display_name", ""),
                    role=Role.ADMIN,
                )
            except ValueError as exc:
                self._send_html("设置", self.app.render_setup_page(str(exc)), status=400)
                return
            self.app.redirect(self, "/login")
            return

        if path == "/register":
            if not self.app.auth_store.has_users():
                self.app.redirect(self, "/setup")
                return
            display_name = fields.get("display_name", "").strip()
            password = fields.get("password", "").strip()
            username = display_name
            try:
                self.app.auth_store.create_user(
                    username,
                    password,
                    display_name=display_name,
                    role=Role.MEMBER,
                    member_id=username,
                    account_status=ACCOUNT_STATUS_PENDING,
                )
            except ValueError as exc:
                self._send_html("注册", self.app.render_register_page(error=str(exc)), status=400)
                return
            self._send_html("注册", self.app.render_register_page(notice="注册申请已提交，请等待管理员审核。"))
            return

        user = self.app.get_current_user(self)
        if user is None:
            self.app.redirect(self, "/login")
            return

        is_admin_mutation = (
            path.startswith("/members/")
            or path in {"/members/add", "/projects/add"}
            or path.startswith("/projects/")
            or (path.startswith("/accounts/") and path.endswith("/approve"))
            or (path.startswith("/members/") and path.endswith("/promote"))
        )
        if is_admin_mutation and user.role not in {Role.ADMIN, Role.PI}:
            self.send_error(403, "Forbidden")
            return

        if path.startswith("/accounts/") and path.endswith("/approve"):
            username = unquote(path[len("/accounts/") : -len("/approve")].strip("/"))
            self._handle_account_approve(user, username)
            return

        if path.startswith("/members/") and path.endswith("/promote"):
            member_id = path[len("/members/") : -len("/promote")].strip("/")
            self._handle_member_promote(user, member_id)
            return

        if path == "/members/add":
            self._handle_member_add(user, fields, fields_multi)
            return
        if path.startswith("/members/") and path.endswith("/edit"):
            member_id = path[len("/members/") : -len("/edit")].strip("/")
            self._handle_member_edit(user, member_id, fields, fields_multi)
            return
        if path.startswith("/members/") and path.endswith("/delete"):
            member_id = path[len("/members/") : -len("/delete")].strip("/")
            self._handle_member_delete(user, member_id)
            return

        if path == "/projects/add":
            self._handle_project_add(user, fields, fields_multi)
            return
        if path.startswith("/projects/") and path.endswith("/edit"):
            project_id = path[len("/projects/") : -len("/edit")].strip("/")
            self._handle_project_edit(user, project_id, fields, fields_multi)
            return
        if path.startswith("/projects/") and path.endswith("/delete"):
            project_id = path[len("/projects/") : -len("/delete")].strip("/")
            self._handle_project_delete(user, project_id)
            return

        if path == "/outputs/add":
            self._handle_output_add(user, fields, fields_multi)
            return
        if path == "/outputs/save":
            self._handle_output_add(user, fields, fields_multi, save_mode="draft")
            return
        if path == "/import/fetch":
            self._handle_import_fetch(user, fields, fields_multi)
            return
        if path == "/import/upload":
            self._handle_import_upload(user)
            return
        if path.startswith("/outputs/") and path.endswith("/edit"):
            output_id = path[len("/outputs/") : -len("/edit")].strip("/")
            self._handle_output_edit(user, output_id, fields, fields_multi, save_mode="submit")
            return
        if path.startswith("/outputs/") and path.endswith("/save"):
            output_id = path[len("/outputs/") : -len("/save")].strip("/")
            self._handle_output_edit(user, output_id, fields, fields_multi, save_mode="draft")
            return
        if path.startswith("/outputs/") and path.endswith("/delete"):
            output_id = path[len("/outputs/") : -len("/delete")].strip("/")
            self._handle_output_delete(user, output_id)
            return

        if path.startswith("/outputs/") and path.endswith("/submit"):
            output_id = path[len("/outputs/") : -len("/submit")].strip("/")
            self._handle_output_transition(user, output_id, "submit")
            return
        if path.startswith("/outputs/") and path.endswith("/approve"):
            output_id = path[len("/outputs/") : -len("/approve")].strip("/")
            self._handle_output_transition(
                user,
                output_id,
                "approve",
                comment=fields.get("comment", ""),
                next_path=fields.get("next", ""),
            )
            return
        if path.startswith("/outputs/") and path.endswith("/return"):
            output_id = path[len("/outputs/") : -len("/return")].strip("/")
            self._handle_output_transition(
                user,
                output_id,
                "return",
                comment=fields.get("comment", ""),
                next_path=fields.get("next", ""),
            )
            return

        self.send_error(404, "Not Found")

    def _handle_member_add(self, user: WebUser, fields: Dict[str, str], fields_multi: Dict[str, List[str]]) -> None:
        try:
            member = Member(
                member_id=fields.get("member_id", "").strip(),
                name=fields.get("name", "").strip(),
                role=Role(fields.get("role", Role.MEMBER.value)),
                email=fields.get("email", "").strip(),
                notes=fields.get("notes", "").strip(),
            )
            self.app.repository.add_member(member)
        except (ValueError, KeyError) as exc:
            self._send_html("Add Member", self.app.render_member_form(user, error=str(exc)), status=400)
            return
        self.app.redirect(self, "/members")

    def _handle_member_edit(self, user: WebUser, member_id: str, fields: Dict[str, str], fields_multi: Dict[str, List[str]]) -> None:
        try:
            member = Member(
                member_id=member_id.strip(),
                name=fields.get("name", "").strip(),
                role=Role(fields.get("role", Role.MEMBER.value)),
                email=fields.get("email", "").strip(),
                notes=fields.get("notes", "").strip(),
            )
            self.app.repository.update_member(member)
        except (ValueError, KeyError) as exc:
            try:
                existing = self.app.repository.get_member(member_id)
            except KeyError:
                self.send_error(404, "Not Found")
                return
            self._send_html("Edit Member", self.app.render_member_form(user, existing, error=str(exc)), status=400)
            return
        self.app.redirect(self, f"/members/{member_id}")

    def _handle_member_delete(self, user: WebUser, member_id: str) -> None:
        try:
            self.app.repository.delete_member(member_id)
        except (ValueError, KeyError) as exc:
            try:
                member = self.app.repository.get_member(member_id)
            except KeyError:
                self.send_error(404, "Not Found")
                return
            self._send_html("Member Detail", self.app.render_member_detail(user, member, notice=str(exc)), status=400)
            return
        self.app.redirect(self, "/members")

    def _handle_member_promote(self, user: WebUser, member_id: str) -> None:
        try:
            promoted = self.app.promote_member_to_admin(member_id, actor=user)
        except (ValueError, KeyError, PermissionError) as exc:
            try:
                member = self.app.repository.get_member(member_id)
            except KeyError:
                self.send_error(404, "Not Found")
                return
            self._send_html("Member Detail", self.app.render_member_detail(user, member, notice=str(exc)), status=400)
            return
        self.app.redirect(self, f"/members/{promoted.member_id}")

    def _handle_account_approve(self, user: WebUser, username: str) -> None:
        if user.role not in {Role.ADMIN, Role.PI}:
            self._send_html(
                "Pending Accounts",
                self.app.render_pending_accounts_page(user, notice="当前账号没有审核权限。"),
                status=403,
            )
            return
        try:
            approved = self.app.auth_store.approve_user(username, approved_by=user.username)
            try:
                self.app.repository.get_member(approved.member_id)
            except KeyError:
                self.app.repository.add_member(
                    Member(
                        member_id=approved.member_id,
                        name=approved.display_name,
                        role=Role.MEMBER,
                    )
                )
        except (ValueError, KeyError) as exc:
            self._send_html(
                "Pending Accounts",
                self.app.render_pending_accounts_page(user, notice=str(exc)),
                status=400,
            )
            return
        self._send_html(
            "Pending Accounts",
            self.app.render_pending_accounts_page(user, notice=f"已通过 {approved.display_name} 的注册申请。"),
        )

    def _handle_project_add(self, user: WebUser, fields: Dict[str, str], fields_multi: Dict[str, List[str]]) -> None:
        try:
            owner_ids = self.app._merge_people_fields(fields_multi, "owner_member_ids", "owner_member_ids_manual")
            start_year = fields.get("start_year", "").strip()
            end_year = fields.get("end_year", "").strip()
            project = Project(
                project_id=fields.get("project_id", "").strip(),
                name=fields.get("name", "").strip(),
                project_type=fields.get("project_type", "").strip(),
                owner_member_ids=owner_ids,
                funding_source=fields.get("funding_source", "").strip(),
                start_year=int(start_year) if start_year else None,
                end_year=int(end_year) if end_year else None,
            )
            self.app.repository.add_project(project)
        except (ValueError, KeyError) as exc:
            self._send_html("Add Project", self.app.render_project_form(user, error=str(exc)), status=400)
            return
        self.app.redirect(self, "/projects")

    def _handle_project_edit(self, user: WebUser, project_id: str, fields: Dict[str, str], fields_multi: Dict[str, List[str]]) -> None:
        try:
            owner_ids = self.app._merge_people_fields(fields_multi, "owner_member_ids", "owner_member_ids_manual")
            start_year = fields.get("start_year", "").strip()
            end_year = fields.get("end_year", "").strip()
            project = Project(
                project_id=project_id.strip(),
                name=fields.get("name", "").strip(),
                project_type=fields.get("project_type", "").strip(),
                owner_member_ids=owner_ids,
                funding_source=fields.get("funding_source", "").strip(),
                start_year=int(start_year) if start_year else None,
                end_year=int(end_year) if end_year else None,
            )
            self.app.repository.update_project(project)
        except (ValueError, KeyError) as exc:
            try:
                existing = self.app.repository.get_project(project_id)
            except KeyError:
                self.send_error(404, "Not Found")
                return
            self._send_html("Edit Project", self.app.render_project_form(user, existing, error=str(exc)), status=400)
            return
        self.app.redirect(self, f"/projects/{project_id}")

    def _handle_project_delete(self, user: WebUser, project_id: str) -> None:
        try:
            self.app.repository.delete_project(project_id)
        except (ValueError, KeyError) as exc:
            try:
                project = self.app.repository.get_project(project_id)
            except KeyError:
                self.send_error(404, "Not Found")
                return
            self._send_html("Project Detail", self.app.render_project_detail(user, project, notice=str(exc)), status=400)
            return
        self.app.redirect(self, "/projects")

    def _handle_output_add(
        self,
        user: WebUser,
        fields: Dict[str, str],
        fields_multi: Dict[str, List[str]],
        *,
        save_mode: str = "submit",
    ) -> None:
        try:
            owner_ids = self.app._merge_people_fields(fields_multi, "owner_member_ids", "owner_member_ids_manual")
            participant_ids = self.app._merge_people_fields(
                fields_multi,
                "participant_member_ids",
                "participant_member_ids_manual",
            )
            project_ids = [v.strip() for v in fields_multi.get("project_ids", []) if v.strip()]
            keywords_raw = fields.get("keywords", "").strip()
            keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
            year = fields.get("year", "").strip()
            output_type = OutputType(fields.get("output_type", OutputType.ARTICLE.value))
            output_year = int(year) if year else None
            output_id = fields.get("output_id", "").strip() or self.app.repository.generate_output_id(
                output_type,
                year=output_year,
            )

            article = None
            patent = None
            if output_type == OutputType.ARTICLE:
                article_type = fields.get("article_type", "").strip()
                if not article_type and save_mode != "draft":
                    raise ValueError("论文成果必须填写文章类型。")
                article = ArticleMetadata(
                    article_type=article_type or "draft_record",
                    journal=fields.get("journal", "").strip(),
                    doi=fields.get("doi", "").strip(),
                    pmid=fields.get("pmid", "").strip(),
                    issn=fields.get("issn", "").strip(),
                    submission_status=fields.get("submission_status", "").strip(),
                )
            if output_type == OutputType.PATENT:
                patent = PatentMetadata(
                    patent_number=fields.get("patent_number", "").strip(),
                    application_number=fields.get("application_number", "").strip(),
                    title=fields.get("patent_title", "").strip(),
                    country_code=fields.get("patent_country", "").strip(),
                    kind_code=fields.get("patent_kind", "").strip(),
                    status=fields.get("patent_status", "").strip(),
                )

            output = ResearchOutput(
                output_id=output_id,
                title=fields.get("title", "").strip(),
                output_type=output_type,
                owner_member_ids=owner_ids,
                participant_member_ids=participant_ids,
                project_ids=project_ids,
                year=output_year,
                keywords=keywords,
                summary=fields.get("summary", "").strip(),
                notes=fields.get("notes", "").strip(),
                article=article,
                patent=patent,
                review_status=ReviewStatus.DRAFT,
            )
            self.app.repository.add_output(output, actor_role=user.role, actor_member_id=user.member_id)
        except (ValueError, KeyError, PermissionError) as exc:
            self._send_html("Add Output", self.app.render_output_form(user, error=str(exc)), status=400)
            return
        if save_mode == "draft":
            self.app.redirect(self, f"/outputs/{output.output_id}")
            return
        self.app.redirect(self, "/outputs")

    def _handle_import_fetch(self, user: WebUser, fields: Dict[str, str], fields_multi: Dict[str, List[str]]) -> None:
        try:
            output = self.app._build_output_from_fetch(fields, user, fields_multi)
            try:
                self.app.repository.add_output(output, actor_role=user.role, actor_member_id=user.member_id)
            except ValueError:
                pass
        except (ValueError, KeyError, PermissionError) as exc:
            self._send_html("Import", self.app.render_import_page(user, error=str(exc)), status=400)
            return
        self.app.redirect(self, f"/outputs/{output.output_id}")

    def _handle_import_upload(self, user: WebUser) -> None:
        try:
            draft, original_name = self._read_uploaded_document()
            if draft is None:
                raise ValueError("未能识别上传文档中的有效文本。")
            output = self.app._build_output_from_document_draft(draft, user)
        except (ValueError, KeyError, PermissionError) as exc:
            self._send_html("Import", self.app.render_import_page(user, error=str(exc)), status=400)
            return
        notice = f"已从 {original_name or draft.source_name or '上传文档'} 识别出可编辑草稿，请确认后提交。"
        form_html = self.app.render_output_form(
            user,
            output,
            notice=notice,
            form_title="文档识别结果",
            submit_label="提交审核",
            prefill_mode=True,
        )
        self._send_html("文档识别结果", form_html)

    def _handle_output_edit(
        self,
        user: WebUser,
        output_id: str,
        fields: Dict[str, str],
        fields_multi: Dict[str, List[str]],
        *,
        save_mode: str = "submit",
    ) -> None:
        try:
            existing = self.app.repository.get_output(output_id)
            owner_ids = self.app._merge_people_fields(fields_multi, "owner_member_ids", "owner_member_ids_manual")
            participant_ids = self.app._merge_people_fields(
                fields_multi,
                "participant_member_ids",
                "participant_member_ids_manual",
            )
            project_ids = [v.strip() for v in fields_multi.get("project_ids", []) if v.strip()]
            keywords_raw = fields.get("keywords", "").strip()
            keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
            year = fields.get("year", "").strip()
            output_type = OutputType(fields.get("output_type", OutputType.ARTICLE.value))

            article = None
            patent = None
            if output_type == OutputType.ARTICLE:
                article_type = fields.get("article_type", "").strip()
                if not article_type:
                    raise ValueError("论文成果必须填写文章类型。")
                article = ArticleMetadata(
                    article_type=article_type,
                    journal=fields.get("journal", "").strip(),
                    doi=fields.get("doi", "").strip(),
                    pmid=fields.get("pmid", "").strip(),
                    issn=fields.get("issn", "").strip(),
                    submission_status=fields.get("submission_status", "").strip(),
                )
            if output_type == OutputType.PATENT:
                patent = PatentMetadata(
                    patent_number=fields.get("patent_number", "").strip(),
                    application_number=fields.get("application_number", "").strip(),
                    title=fields.get("patent_title", "").strip(),
                    country_code=fields.get("patent_country", "").strip(),
                    kind_code=fields.get("patent_kind", "").strip(),
                    status=fields.get("patent_status", "").strip(),
                )

            output = ResearchOutput(
                output_id=output_id.strip(),
                title=fields.get("title", "").strip(),
                output_type=output_type,
                owner_member_ids=owner_ids,
                participant_member_ids=participant_ids,
                project_ids=project_ids,
                year=int(year) if year else None,
                keywords=keywords,
                summary=fields.get("summary", "").strip(),
                notes=fields.get("notes", "").strip(),
                review_status=ReviewStatus.DRAFT if save_mode == "draft" else existing.review_status,
                article=article,
                patent=patent,
                created_at=existing.created_at,
            )
            self.app.repository.update_output(output, actor_role=user.role, actor_member_id=user.member_id)
        except (ValueError, KeyError, PermissionError) as exc:
            try:
                existing = self.app.repository.get_output(output_id)
            except KeyError:
                self.send_error(404, "Not Found")
                return
            self._send_html("Edit Output", self.app.render_output_form(user, existing, error=str(exc)), status=400)
            return
        if save_mode == "draft":
            self.app.redirect(self, f"/outputs/{output_id}")
            return
        self.app.redirect(self, f"/outputs/{output_id}")

    def _handle_output_delete(self, user: WebUser, output_id: str) -> None:
        try:
            self.app.repository.delete_output(output_id, actor_role=user.role, actor_member_id=user.member_id)
        except (ValueError, KeyError, PermissionError) as exc:
            try:
                output = self.app.repository.get_output(output_id)
            except KeyError:
                self.send_error(404, "Not Found")
                return
            self._send_html("Output Detail", self.app.render_output_detail(user, output, notice=str(exc)), status=400)
            return
        self.app.redirect(self, "/outputs")

    def _handle_output_transition(
        self,
        user: WebUser,
        output_id: str,
        action: str,
        *,
        comment: str = "",
        next_path: str = "",
    ) -> None:
        try:
            if action == "submit":
                self.app.repository.submit_output(output_id, actor_role=user.role, actor_member_id=user.member_id)
            elif action == "approve":
                self.app.repository.approve_output(
                    output_id,
                    actor_role=user.role,
                    actor_member_id=user.member_id,
                    comment=comment or "Approved from web UI.",
                )
            elif action == "return":
                self.app.repository.return_output(
                    output_id,
                    actor_role=user.role,
                    actor_member_id=user.member_id,
                    comment=comment or "Returned from web UI.",
                )
            else:
                raise ValueError(f"Unsupported action: {action}")
        except (KeyError, PermissionError, ValueError) as exc:
            try:
                output = self.app.repository.get_output(output_id)
            except KeyError:
                self.send_error(404, "Not Found")
                return
            self._send_html(output.title, self.app.render_output_detail(user, output, notice=str(exc)), status=400)
            return
        if not next_path and action in {"approve", "return"}:
            next_path = "/reviews" if user.role in {Role.ADMIN, Role.PI} else f"/outputs/{output_id}"
        self.app.redirect(self, next_path or f"/outputs/{output_id}")

    def _read_uploaded_document(self) -> Tuple[Optional[DocumentImportDraft], str]:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ValueError("上传文档请求必须使用 multipart/form-data。")
        env = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
        }
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ=env, keep_blank_values=True)
        item = form["document_file"] if "document_file" in form else None
        if item is None or not getattr(item, "filename", ""):
            raise ValueError("请选择要上传的文档。")
        file_name = item.filename or "document"
        file_bytes = item.file.read()
        if not isinstance(file_bytes, (bytes, bytearray)):
            raise ValueError("上传文档读取失败。")
        draft = infer_document_draft(file_name, bytes(file_bytes))
        return draft, file_name

    def _logout(self) -> None:
        token = self.app._get_cookie(self, SESSION_COOKIE_NAME)
        if token:
            self.app.sessions.revoke(token)
        self.send_response(303)
        self.app.clear_session_cookie(self)
        self.send_header("Location", "/login")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_form_fields(self) -> Dict[str, str]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        parsed = parse_qs(raw, keep_blank_values=True)
        return {key: values[0] if values else "" for key, values in parsed.items()}

    def _send_html(self, title: str, document: str, *, status: int = 200) -> None:
        body = document.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_excel_export(self, user: WebUser) -> None:
        """处理Excel导出请求。"""
        if not can_perform(user.role, Permission.EXPORT, actor_member_id=user.member_id):
            self.send_error(403, "Forbidden")
            return
        try:
            from .excel_export import export_to_excel
            import tempfile
            import os

            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.xlsx', delete=False) as tmp:
                tmp_path = tmp.name

            try:
                # 导出到临时文件
                export_to_excel(self.app.repository, tmp_path)

                # 读取文件内容
                with open(tmp_path, 'rb') as f:
                    content = f.read()

                # 发送文件
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Disposition", "attachment; filename=\"research_outputs.xlsx\"")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            finally:
                # 清理临时文件
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        except ImportError:
            self.send_error(500, "需要安装 openpyxl")
        except Exception as e:
            self.send_error(500, f"导出失败: {str(e)}")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def create_web_server(
    *,
    data_dir: Path | str,
    auth_path: Path | str,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> ThreadingHTTPServer:
    app = WebApplication(data_dir=data_dir, auth_path=auth_path)

    class _Server(ThreadingHTTPServer):
        def __init__(self, server_address, RequestHandlerClass):
            super().__init__(server_address, RequestHandlerClass)
            self.app = app

    return _Server((host, port), LocalWebRequestHandler)
