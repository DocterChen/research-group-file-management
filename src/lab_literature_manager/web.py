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

from .models import Member, OutputType, Permission, Project, ResearchOutput, ReviewStatus, Role
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
            ("dashboard", "/", "Dashboard"),
            ("members", "/members", "Members"),
            ("projects", "/projects", "Projects"),
            ("outputs", "/outputs", "Outputs"),
            ("logout", "/logout", "Log out"),
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
              <h1>Local Research Manager</h1>
              <p>Group成果与审核工作台</p>
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
                  <h1>Local Research Manager</h1>
                  <p>Group成果与审核工作台</p>
                </div>
              </div>
              <h1>让课题组成果管理回到一个清晰的页面里。</h1>
              <p>登录后可以查看成员、项目和成果状态，直接提交与审核，所有数据都保存在本地 JSON 工作区里。</p>
              <div class="login-stats">
                <div class="login-stat"><strong>Login</strong><span>本地账号认证</span></div>
                <div class="login-stat"><strong>Views</strong><span>仪表盘与图表</span></div>
                <div class="login-stat"><strong>Workflow</strong><span>提交与审核闭环</span></div>
                <div class="login-stat"><strong>Files</strong><span>JSON 持久化</span></div>
              </div>
            </div>
            <div class="login-panel">
              <h2 style="margin:0 0 10px;">Sign in</h2>
              <p class="muted" style="margin-top:0;">Use your local workspace credentials.</p>
              {error_html}
              <form method="post" action="/login">
                <div class="field">
                  <label for="username">Username</label>
                  <input id="username" name="username" autocomplete="username" required />
                </div>
                <div class="field">
                  <label for="password">Password</label>
                  <input id="password" name="password" type="password" autocomplete="current-password" required />
                </div>
                <div class="button-row">
                  <button class="button primary" type="submit">Sign in</button>
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
                  <h1>Local Research Manager</h1>
                  <p>Group成果与审核工作台</p>
                </div>
              </div>
              <h1>Create workspace access.</h1>
              <p>首次进入时先创建一个管理员账号，之后就可以登录并开始维护成员、项目和成果数据。</p>
            </div>
            <div class="login-panel">
              <h2 style="margin:0 0 10px;">Workspace setup</h2>
              {error_html}
              <form method="post" action="/setup">
                <div class="field">
                  <label for="username">Admin username</label>
                  <input id="username" name="username" autocomplete="username" required />
                </div>
                <div class="field">
                  <label for="display_name">Display name</label>
                  <input id="display_name" name="display_name" autocomplete="name" required />
                </div>
                <div class="field">
                  <label for="password">Password</label>
                  <input id="password" name="password" type="password" autocomplete="new-password" required />
                </div>
                <div class="button-row">
                  <button class="button primary" type="submit">Create admin</button>
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
              <h2>Research Command Center</h2>
              <div class="subtle">浏览成果、跟踪状态、查看分布图。</div>
            </div>
            <div class="button-row">
              <a class="button secondary" href="/outputs">Open outputs</a>
            </div>
          </div>
          <div class="grid cards">
            {self._metric_card("Total outputs", str(summary["total_outputs"]), "所有成果记录")}
            {self._metric_card("Members", str(len(members)), "本地成员档案")}
            {self._metric_card("Projects", str(len(projects)), "关联项目与课题")}
            {self._metric_card("Approved", str(status_counts.get(ReviewStatus.APPROVED.value, 0)), "已通过审核")}
          </div>
          <div class="grid panels">
            <article class="card">
              <div class="panel-title">
                <h3>Outputs by type</h3>
                <span>数量分布</span>
              </div>
              {self._bar_chart(type_counts, accent_class="")}
            </article>
            <article class="card">
              <div class="panel-title">
                <h3>Review status</h3>
                <span>流程状态</span>
              </div>
              {self._bar_chart(status_counts, accent_class="status-fill")}
              <div style="height:16px"></div>
              <div class="panel-title">
                <h3>Outputs by year</h3>
                <span>发表/归档时间</span>
              </div>
              {self._bar_chart(year_counts, accent_class="")}
            </article>
          </div>
          <article class="card">
            <div class="panel-title">
              <h3>Recent outputs</h3>
              <span>latest records</span>
            </div>
            {self._output_table(recent_outputs)}
          </article>
        </section>
        """
        return self.render_layout("Dashboard", body, active_section="dashboard", current_user=current_user)

    def render_members_page(self, current_user: WebUser) -> str:
        members = self.repository.list_members()
        rows = "".join(
            f"<tr><td>{html.escape(member.member_id)}</td><td>{html.escape(member.name)}</td><td>{html.escape(member.role.value)}</td><td>{html.escape(member.email or '-')}</td></tr>"
            for member in members
        ) or '<tr><td colspan="4" class="muted">No members found.</td></tr>'
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>Members</h2>
              <div class="subtle">课题组成员与角色档案。</div>
            </div>
          </div>
          <article class="card">
            <table class="table">
              <thead><tr><th>ID</th><th>Name</th><th>Role</th><th>Email</th></tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </article>
        </section>
        """
        return self.render_layout("Members", body, active_section="members", current_user=current_user)

    def render_projects_page(self, current_user: WebUser) -> str:
        projects = self.repository.list_projects()
        rows = "".join(
            f"<tr><td>{html.escape(project.project_id)}</td><td>{html.escape(project.name)}</td><td>{html.escape(project.project_type)}</td><td>{html.escape(', '.join(project.owner_member_ids) or '-')}</td></tr>"
            for project in projects
        ) or '<tr><td colspan="4" class="muted">No projects found.</td></tr>'
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>Projects</h2>
              <div class="subtle">课题、基金与合作项目。</div>
            </div>
          </div>
          <article class="card">
            <table class="table">
              <thead><tr><th>ID</th><th>Name</th><th>Type</th><th>Owners</th></tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </article>
        </section>
        """
        return self.render_layout("Projects", body, active_section="projects", current_user=current_user)

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
        ) or '<tr><td colspan="5" class="muted">No outputs found.</td></tr>'
        body = f"""
        <section class="stack">
          <div class="topbar">
            <div>
              <h2>Outputs</h2>
              <div class="subtle">成果记录、状态和项目关联。</div>
            </div>
          </div>
          <article class="card">
            <table class="table">
              <thead><tr><th>ID</th><th>Title</th><th>Type</th><th>Status</th><th>Year</th></tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </article>
        </section>
        """
        return self.render_layout("Outputs", body, active_section="outputs", current_user=current_user)

    def render_output_detail(self, current_user: WebUser, output: ResearchOutput, notice: str = "") -> str:
        actions = []
        if can_perform(current_user.role, Permission.EDIT, output=output, actor_member_id=current_user.member_id):
            actions.append(
                f'<form method="post" action="/outputs/{html.escape(output.output_id)}/submit" style="display:inline-block;margin-right:10px;"><button class="button primary" type="submit">Submit for review</button></form>'
            )
        if can_perform(current_user.role, Permission.REVIEW, output=output, actor_member_id=current_user.member_id):
            actions.append(
                f'<form method="post" action="/outputs/{html.escape(output.output_id)}/approve" style="display:inline-block;"><input type="hidden" name="comment" value="Approved from web UI" /><button class="button secondary" type="submit">Approve</button></form>'
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
                <h3>Overview</h3>
                <span>{self._status_badge(output.review_status)}</span>
              </div>
              <div class="kv">
                <div><span>Status</span><span>{html.escape(output.review_status.value)}</span></div>
                <div><span>Year</span><span>{html.escape(str(output.year) if output.year is not None else '-')}</span></div>
                <div><span>Owners</span><span>{html.escape(', '.join(output.owner_member_ids))}</span></div>
                <div><span>Participants</span><span>{html.escape(', '.join(output.participant_member_ids) or '-')}</span></div>
                <div><span>Projects</span><span>{html.escape(', '.join(output.project_ids) or '-')}</span></div>
                <div><span>Keywords</span><span>{html.escape(', '.join(output.keywords) or '-')}</span></div>
              </div>
            </article>
            <article class="card">
              <div class="panel-title">
                <h3>Metadata</h3>
                <span>structured fields</span>
              </div>
              {self._detail_metadata(output)}
            </article>
          </div>
          <article class="card">
            <div class="panel-title">
              <h3>Notes</h3>
              <span>summary and comments</span>
            </div>
            <p class="muted">{html.escape(output.summary or 'No summary provided.')}</p>
            <p class="muted">{html.escape(output.notes or 'No notes provided.')}</p>
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
            return '<div class="muted">No data yet.</div>'
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
        ) or '<tr><td colspan="4" class="muted">No outputs found.</td></tr>'
        return f"""
        <table class="table">
          <thead><tr><th>ID</th><th>Title</th><th>Type</th><th>Status</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
        """

    def _status_badge(self, status: ReviewStatus) -> str:
        return f'<span class="badge status-{html.escape(status.value)}">{html.escape(status.value.title())}</span>'

    def _detail_metadata(self, output: ResearchOutput) -> str:
        chunks = [
            f"<div class='kv'><div><span>Created</span><span>{html.escape(output.created_at)}</span></div><div><span>Updated</span><span>{html.escape(output.updated_at)}</span></div></div>"
        ]
        if output.article:
            chunks.append(
                f"""
                <div class="kv">
                  <div><span>Article type</span><span>{html.escape(output.article.article_type)}</span></div>
                  <div><span>Journal</span><span>{html.escape(output.article.journal or '-')}</span></div>
                  <div><span>DOI</span><span>{html.escape(output.article.doi or '-')}</span></div>
                  <div><span>Submission</span><span>{html.escape(output.article.submission_status or '-')}</span></div>
                </div>
                """
            )
        return "".join(chunks)


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
        if path == "/members":
            self._send_html("Members", self.app.render_members_page(user))
            return
        if path == "/projects":
            self._send_html("Projects", self.app.render_projects_page(user))
            return
        if path == "/outputs":
            self._send_html("Outputs", self.app.render_outputs_page(user))
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
        fields = self._read_form_fields()

        if path == "/login":
            if not self.app.auth_store.has_users():
                self.app.redirect(self, "/setup")
                return
            username = fields.get("username", "")
            password = fields.get("password", "")
            user = self.app.auth_store.authenticate(username, password)
            if user is None:
                self._send_html("Login", self.app.render_login_page("Invalid username or password."), status=401)
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
                self._send_html("Setup", self.app.render_setup_page(str(exc)), status=400)
                return
            self.app.redirect(self, "/login")
            return

        user = self.app.get_current_user(self)
        if user is None:
            self.app.redirect(self, "/login")
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
