"""Local browser UI for the research output manager."""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from .models import ArticleMetadata, Member, OutputType, Permission, Project, ResearchOutput, ReviewStatus, Role
from .permissions import can_perform
from .repository import ResearchRepository

AUTH_SCHEMA_VERSION = 1
SESSION_COOKIE_NAME = "litman_session"
SESSION_TTL_HOURS = 8
PASSWORD_ITERATIONS = 180_000


@dataclass(frozen=True)
class WebUser:
    username: str
    password_hash: str
    password_salt: str
    display_name: str
    role: Role
    member_id: str = ""
    created_at: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "username": self.username,
            "password_hash": self.password_hash,
            "password_salt": self.password_salt,
            "display_name": self.display_name,
            "role": self.role.value,
            "member_id": self.member_id,
            "created_at": self.created_at,
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
        )


@dataclass
class SessionRecord:
    username: str
    expires_at: datetime


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
            )
            users.append(user)
            self._save_users(users)
            return user

    def authenticate(self, username: str, password: str) -> Optional[WebUser]:
        user = self.get_user(username)
        if user is None:
            return None
        salt = base64.b64decode(user.password_salt.encode("ascii"))
        expected = user.password_hash
        actual = self._hash_password(password, salt)
        if hmac.compare_digest(expected, actual):
            return user
        return None

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
    ) -> str:
        nav = self._render_nav(active_section=active_section, current_user=current_user)
        notice_html = f'<div class="notice">{html.escape(notice)}</div>' if notice else ""
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
    @media (max-width: 1080px) {{
      .shell {{ grid-template-columns: 1fr; }}
      .sidebar {{ border-right: none; border-bottom: 1px solid var(--line); }}
      .cards, .panels, .detail-grid, .login-card {{ grid-template-columns: 1fr; }}
      .bar-row {{ grid-template-columns: 1fr; }}
      .content {{ padding: 18px; }}
    }}
  </style>
</head>
<body>
  {notice_html}
  <div class="shell">
    {nav}
    <main class="content">
      {body}
    </main>
  </div>
</body>
</html>"""

    def _render_nav(self, *, active_section: str, current_user: Optional[WebUser]) -> str:
        if current_user is None:
            if self.auth_store.has_users():
                return ""
            return ""
        links = [
            ("dashboard", "/", "仪表盘"),
            ("members", "/members", "成员管理"),
            ("projects", "/projects", "项目管理"),
            ("outputs", "/outputs", "成果管理"),
            ("logout", "/logout", "退出登录"),
        ]
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
              <h1>课题组科研成果管理系统</h1>
              <p>成果管理与审核工作台</p>
            </div>
          </div>
          <div class="user-pill">
            <div class="avatar">{html.escape(avatar)}</div>
            <div>
              <strong>{html.escape(current_user.display_name)}</strong><br />
              <span class="muted">{html.escape(current_user.role.value)}</span>
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
        return f"""
        <div class="login-shell">
          <section class="login-card">
            <div class="login-hero">
              <div class="brand" style="margin-bottom: 30px;">
                <div class="brand-mark"></div>
                <div>
                  <h1>课题组科研成果管理系统</h1>
                  <p>成果管理与审核工作台</p>
                </div>
              </div>
              <h1>让课题组成果管理回到一个清晰的页面里。</h1>
              <p>登录后可以查看成员、项目和成果状态，直接提交与审核，所有数据都保存在本地 JSON 工作区里。</p>
              <div class="login-stats">
                <div class="login-stat"><strong>登录</strong><span>本地账号认证</span></div>
                <div class="login-stat"><strong>仪表盘</strong><span>可视化图表</span></div>
                <div class="login-stat"><strong>工作流</strong><span>提交与审核闭环</span></div>
                <div class="login-stat"><strong>文件</strong><span>JSON 持久化</span></div>
              </div>
            </div>
            <div class="login-panel">
              <h2 style="margin:0 0 10px;">登录</h2>
              <p class="muted" style="margin-top:0;">使用本地工作区账号登录</p>
              {error_html}
              <form method="post" action="/login">
                <div class="field">
                  <label for="username">用户名</label>
                  <input id="username" name="username" autocomplete="username" required />
                </div>
                <div class="field">
                  <label for="password">密码</label>
                  <input id="password" name="password" type="password" autocomplete="current-password" required />
                </div>
                <div class="button-row">
                  <button class="button primary" type="submit">登录</button>
                </div>
              </form>
            </div>
          </section>
        </div>
        """

    def render_setup_page(self, error: str = "") -> str:
        error_html = f'<div class="notice">{html.escape(error)}</div>' if error else ""
        return f"""
        <div class="login-shell">
          <section class="login-card">
            <div class="login-hero">
              <div class="brand" style="margin-bottom: 30px;">
                <div class="brand-mark"></div>
                <div>
                  <h1>课题组科研成果管理系统</h1>
                  <p>成果管理与审核工作台</p>
                </div>
              </div>
              <h1>创建工作区访问权限</h1>
              <p>首次进入时先创建一个管理员账号，之后就可以登录并开始维护成员、项目和成果数据。</p>
            </div>
            <div class="login-panel">
              <h2 style="margin:0 0 10px;">工作区设置</h2>
              {error_html}
              <form method="post" action="/setup">
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

    def render_dashboard(self, current_user: WebUser) -> str:
        summary = self.repository.build_summary()
        outputs = self.repository.list_outputs()
        members = self.repository.list_members()
        projects = self.repository.list_projects()
        recent_outputs = outputs[:5]
        type_counts = summary["by_type"]
        status_counts = summary["by_review_status"]
        year_counts = summary["by_year"]
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>成果指挥中心</h2>
              <div class="subtle">浏览成果、跟踪状态、查看分布图。</div>
            </div>
            <div class="button-row">
              <a class="button secondary" href="/outputs">查看成果</a>
              <a class="button secondary" href="/export/excel">导出Excel</a>
            </div>
          </div>
          <div class="grid cards">
            {self._metric_card("总成果数", str(summary["total_outputs"]), "所有成果记录")}
            {self._metric_card("成员数", str(len(members)), "本地成员档案")}
            {self._metric_card("项目数", str(len(projects)), "关联项目与课题")}
            {self._metric_card("已审核", str(status_counts.get(ReviewStatus.APPROVED.value, 0)), "已通过审核")}
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
            f"<td>{html.escape(member.role.value)}</td>"
            f"<td>{html.escape(member.email or '-')}</td>"
            f"</tr>"
            for member in members
        ) or '<tr><td colspan="4" class="muted">暂无成员数据。</td></tr>'
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
              <thead><tr><th>编号</th><th>姓名</th><th>角色</th><th>邮箱</th></tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </article>
        </section>
        """
        return self.render_layout("成员管理", body, active_section="members", current_user=current_user)

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
        outputs = self.repository.list_outputs()
        rows = "".join(
            f"<tr>"
            f"<td><a href=\"/outputs/{html.escape(output.output_id)}\">{html.escape(output.output_id)}</a></td>"
            f"<td>{html.escape(output.title)}</td>"
            f"<td>{html.escape(output.output_type.value)}</td>"
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

    def render_output_detail(self, current_user: WebUser, output: ResearchOutput, notice: str = "") -> str:
        actions = []
        if can_perform(current_user.role, Permission.EDIT, output=output, actor_member_id=current_user.member_id):
            actions.append(
                f'<form method="post" action="/outputs/{html.escape(output.output_id)}/submit" style="display:inline-block;margin-right:10px;"><button class="button primary" type="submit">提交审核</button></form>'
            )
        if can_perform(current_user.role, Permission.REVIEW, output=output, actor_member_id=current_user.member_id):
            actions.append(
                f'<form method="post" action="/outputs/{html.escape(output.output_id)}/approve" style="display:inline-block;"><input type="hidden" name="comment" value="通过Web界面审核通过" /><button class="button secondary" type="submit">批准</button></form>'
            )
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>{html.escape(output.title)}</h2>
              <div class="subtle">{html.escape(output.output_id)} · {html.escape(output.output_type.value)}</div>
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
                <div><span>状态</span><span>{html.escape(output.review_status.value)}</span></div>
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

    def _metric_card(self, label: str, value: str, hint: str) -> str:
        return f"""
        <article class="card">
          <div class="metric-label">{html.escape(label)}</div>
          <div class="metric-value">{html.escape(value)}</div>
          <div class="metric-hint">{html.escape(hint)}</div>
        </article>
        """

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
            f"<tr><td><a href=\"/outputs/{html.escape(output.output_id)}\">{html.escape(output.output_id)}</a></td><td>{html.escape(output.title)}</td><td>{html.escape(output.output_type.value)}</td><td>{self._status_badge(output.review_status)}</td></tr>"
            for output in outputs
        ) or '<tr><td colspan="4" class="muted">暂无成果数据。</td></tr>'
        return f"""
        <table class="table">
          <thead><tr><th>编号</th><th>标题</th><th>类型</th><th>状态</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
        """

    def _status_badge(self, status: ReviewStatus) -> str:
        return f'<span class="badge status-{html.escape(status.value)}">{html.escape(status.value.title())}</span>'

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
            f'<option value="{role.value}"{" selected" if member and member.role == role else ""}>{html.escape(role.value)}</option>'
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
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>{html.escape(member.name)}</h2>
              <div class="subtle">{html.escape(member.member_id)} · {html.escape(member.role.value)}</div>
            </div>
            <div class="button-row">
              <a class="button primary" href="/members/{html.escape(member.member_id)}/edit">编辑</a>
              <form method="post" action="/members/{html.escape(member.member_id)}/delete" style="display:inline-block;" onsubmit="return confirm('确认删除成员 {html.escape(member.name)}？此操作不可恢复。');">
                <button class="button secondary" type="submit">删除</button>
              </form>
            </div>
          </div>
          <article class="card">
            <div class="kv">
              <div><span>成员编号</span><span>{html.escape(member.member_id)}</span></div>
              <div><span>姓名</span><span>{html.escape(member.name)}</span></div>
              <div><span>角色</span><span>{html.escape(member.role.value)}</span></div>
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
        self, current_user: WebUser, output: Optional[ResearchOutput] = None, error: str = ""
    ) -> str:
        is_edit = output is not None
        title = "编辑成果" if is_edit else "添加成果"
        action = f"/outputs/{html.escape(output.output_id)}/edit" if is_edit else "/outputs/add"
        output_id_field = (
            f'<input id="output_id" name="output_id" value="{html.escape(output.output_id)}" readonly />'
            if is_edit
            else '<input id="output_id" name="output_id" required />'
        )
        error_html = f'<div class="notice">{html.escape(error)}</div>' if error else ""

        # Output type options
        output_type_options = "".join(
            f'<option value="{ot.value}"{" selected" if output and output.output_type == ot else ""}>{html.escape(ot.value)}</option>'
            for ot in OutputType
        )

        # Members for checkboxes
        members = self.repository.list_members()
        owner_checkboxes = "".join(
            f'<label style="display:flex;gap:8px;padding:8px;"><input type="checkbox" name="owner_member_ids" value="{html.escape(m.member_id)}"{" checked" if output and m.member_id in output.owner_member_ids else ""} /><span>{html.escape(m.name)} ({html.escape(m.member_id)})</span></label>'
            for m in members
        )
        participant_checkboxes = "".join(
            f'<label style="display:flex;gap:8px;padding:8px;"><input type="checkbox" name="participant_member_ids" value="{html.escape(m.member_id)}"{" checked" if output and m.member_id in output.participant_member_ids else ""} /><span>{html.escape(m.name)} ({html.escape(m.member_id)})</span></label>'
            for m in members
        )

        # Projects for checkboxes
        projects = self.repository.list_projects()
        project_checkboxes = "".join(
            f'<label style="display:flex;gap:8px;padding:8px;"><input type="checkbox" name="project_ids" value="{html.escape(p.project_id)}"{" checked" if output and p.project_id in output.project_ids else ""} /><span>{html.escape(p.name)} ({html.escape(p.project_id)})</span></label>'
            for p in projects
        )

        # Article fields (shown/hidden based on output type)
        article_display = 'style="display:block;"' if output and output.output_type == OutputType.ARTICLE else 'style="display:none;"'
        article = output.article if output and output.article else None

        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>{title}</h2>
              <div class="subtle">{'修改成果信息' if is_edit else '添加新成果记录'}</div>
            </div>
          </div>
          <article class="card">
            {error_html}
            <form method="post" action="{action}" class="stack">
              <div class="field">
                <label for="output_id">成果编号 *</label>
                {output_id_field}
              </div>
              <div class="field">
                <label for="title">成果标题 *</label>
                <input id="title" name="title" value="{html.escape(output.title) if output else ''}" required />
              </div>
              <div class="field">
                <label for="output_type">成果类型 *</label>
                <select id="output_type" name="output_type" required style="width:100%;padding:12px 14px;border-radius:14px;border:1px solid var(--line);" onchange="toggleArticleFields(this.value)">{output_type_options}</select>
              </div>
              <div class="field">
                <label for="year">年份</label>
                <input id="year" name="year" type="number" min="1900" max="2100" value="{output.year if output and output.year else ''}" />
              </div>
              <div class="field">
                <label>负责人 *</label>
                <div style="border:1px solid var(--line);border-radius:14px;padding:8px;max-height:200px;overflow-y:auto;">
                  {owner_checkboxes if owner_checkboxes else '<p class="muted">暂无成员。</p>'}
                </div>
              </div>
              <div class="field">
                <label>参与人</label>
                <div style="border:1px solid var(--line);border-radius:14px;padding:8px;max-height:200px;overflow-y:auto;">
                  {participant_checkboxes if participant_checkboxes else '<p class="muted">暂无成员。</p>'}
                </div>
              </div>
              <div class="field">
                <label>关联项目</label>
                <div style="border:1px solid var(--line);border-radius:14px;padding:8px;max-height:200px;overflow-y:auto;">
                  {project_checkboxes if project_checkboxes else '<p class="muted">暂无项目。</p>'}
                </div>
              </div>
              <div class="field">
                <label for="keywords">关键词（逗号分隔）</label>
                <input id="keywords" name="keywords" value="{html.escape(', '.join(output.keywords)) if output else ''}" placeholder="keyword1, keyword2, keyword3" />
              </div>
              <div class="field">
                <label for="summary">摘要</label>
                <textarea id="summary" name="summary" rows="4" style="width:100%;resize:vertical;">{html.escape(output.summary) if output else ''}</textarea>
              </div>
              <div class="field">
                <label for="notes">备注</label>
                <textarea id="notes" name="notes" rows="3" style="width:100%;resize:vertical;">{html.escape(output.notes) if output else ''}</textarea>
              </div>

              <div id="article-fields" {article_display}>
                <h3 style="margin-top:20px;margin-bottom:16px;">文章专属字段</h3>
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

              <div class="button-row">
                <button class="button primary" type="submit">{'保存' if is_edit else '添加'}</button>
                <a class="button secondary" href="/outputs">取消</a>
              </div>
            </form>
            <script>
              function toggleArticleFields(outputType) {{
                const articleFields = document.getElementById('article-fields');
                const articleTypeInput = document.getElementById('article_type');
                if (outputType === 'article') {{
                  articleFields.style.display = 'block';
                  articleTypeInput.required = true;
                }} else {{
                  articleFields.style.display = 'none';
                  articleTypeInput.required = false;
                }}
              }}
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
        if path == "/members":
            self._send_html("Members", self.app.render_members_page(user))
            return
        if path == "/members/add":
            self._send_html("Add Member", self.app.render_member_form(user))
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
            self._send_html(output.title, self.app.render_output_detail(user, output))
            return
        self.send_error(404, "Not Found")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0") or "0")
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
            user = self.app.auth_store.authenticate(username, password)
            if user is None:
                self._send_html("登录", self.app.render_login_page("用户名或密码错误。"), status=401)
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

        user = self.app.get_current_user(self)
        if user is None:
            self.app.redirect(self, "/login")
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
        if path.startswith("/outputs/") and path.endswith("/edit"):
            output_id = path[len("/outputs/") : -len("/edit")].strip("/")
            self._handle_output_edit(user, output_id, fields, fields_multi)
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
            self._handle_output_transition(user, output_id, "approve", comment=fields.get("comment", ""))
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

    def _handle_project_add(self, user: WebUser, fields: Dict[str, str], fields_multi: Dict[str, List[str]]) -> None:
        try:
            owner_ids = [v.strip() for v in fields_multi.get("owner_member_ids", []) if v.strip()]
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
            owner_ids = [v.strip() for v in fields_multi.get("owner_member_ids", []) if v.strip()]
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

    def _handle_output_add(self, user: WebUser, fields: Dict[str, str], fields_multi: Dict[str, List[str]]) -> None:
        try:
            owner_ids = [v.strip() for v in fields_multi.get("owner_member_ids", []) if v.strip()]
            participant_ids = [v.strip() for v in fields_multi.get("participant_member_ids", []) if v.strip()]
            project_ids = [v.strip() for v in fields_multi.get("project_ids", []) if v.strip()]
            keywords_raw = fields.get("keywords", "").strip()
            keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
            year = fields.get("year", "").strip()
            output_type = OutputType(fields.get("output_type", OutputType.ARTICLE.value))

            article = None
            if output_type == OutputType.ARTICLE:
                article_type = fields.get("article_type", "").strip()
                if not article_type:
                    raise ValueError("Article type is required for article outputs.")
                article = ArticleMetadata(
                    article_type=article_type,
                    journal=fields.get("journal", "").strip(),
                    doi=fields.get("doi", "").strip(),
                    pmid=fields.get("pmid", "").strip(),
                    issn=fields.get("issn", "").strip(),
                    submission_status=fields.get("submission_status", "").strip(),
                )

            output = ResearchOutput(
                output_id=fields.get("output_id", "").strip(),
                title=fields.get("title", "").strip(),
                output_type=output_type,
                owner_member_ids=owner_ids,
                participant_member_ids=participant_ids,
                project_ids=project_ids,
                year=int(year) if year else None,
                keywords=keywords,
                summary=fields.get("summary", "").strip(),
                notes=fields.get("notes", "").strip(),
                article=article,
            )
            self.app.repository.add_output(output, actor_role=user.role, actor_member_id=user.member_id)
        except (ValueError, KeyError, PermissionError) as exc:
            self._send_html("Add Output", self.app.render_output_form(user, error=str(exc)), status=400)
            return
        self.app.redirect(self, "/outputs")

    def _handle_output_edit(self, user: WebUser, output_id: str, fields: Dict[str, str], fields_multi: Dict[str, List[str]]) -> None:
        try:
            existing = self.app.repository.get_output(output_id)
            owner_ids = [v.strip() for v in fields_multi.get("owner_member_ids", []) if v.strip()]
            participant_ids = [v.strip() for v in fields_multi.get("participant_member_ids", []) if v.strip()]
            project_ids = [v.strip() for v in fields_multi.get("project_ids", []) if v.strip()]
            keywords_raw = fields.get("keywords", "").strip()
            keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
            year = fields.get("year", "").strip()
            output_type = OutputType(fields.get("output_type", OutputType.ARTICLE.value))

            article = None
            if output_type == OutputType.ARTICLE:
                article_type = fields.get("article_type", "").strip()
                if not article_type:
                    raise ValueError("Article type is required for article outputs.")
                article = ArticleMetadata(
                    article_type=article_type,
                    journal=fields.get("journal", "").strip(),
                    doi=fields.get("doi", "").strip(),
                    pmid=fields.get("pmid", "").strip(),
                    issn=fields.get("issn", "").strip(),
                    submission_status=fields.get("submission_status", "").strip(),
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
                review_status=existing.review_status,
                article=article,
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

    def _handle_output_transition(self, user: WebUser, output_id: str, action: str, *, comment: str = "") -> None:
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
        self.app.redirect(self, f"/outputs/{output_id}")

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
