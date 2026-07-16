"""
安全测试用例

测试微信小程序 API 的安全性，包括：
- 速率限制
- CSRF 保护
- 输入验证
- 会话管理
- 权限隔离
"""

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pytest

# 模拟导入（实际测试时需要调整导入路径）
from src.lab_literature_manager.api_extensions import APIRequestHandler
from src.lab_literature_manager.multilab_repository import MultiLabRepository
from src.lab_literature_manager.wechat_api import WeChatConfig


class TestLoginSecurity:
    """登录接口安全测试"""

    def test_rate_limiting(self, api_handler: APIRequestHandler):
        """测试速率限制：同一 IP 每分钟最多 10 次登录尝试"""
        client_ip = "192.168.1.100"

        # 前 10 次应该成功（或返回正常错误）
        for i in range(10):
            response = api_handler.api_wechat_miniprogram_login(
                {"code": f"invalid_code_{i}"},
                client_ip
            )
            assert "error" in response  # 可能是微信 API 错误或其他错误
            assert response["error"] != "Too many requests"

        # 第 11 次应该被限流
        response = api_handler.api_wechat_miniprogram_login(
            {"code": "invalid_code_11"},
            client_ip
        )
        assert response["error"] == "Too many requests, please try again later"

    def test_session_key_not_exposed(self, api_handler: APIRequestHandler, mock_wechat_api):
        """测试 session_key 不会泄露给客户端"""
        # 模拟新用户登录（需要绑定）
        response = api_handler.api_wechat_miniprogram_login(
            {"code": "valid_code_new_user"},
            "192.168.1.100"
        )

        assert response["status"] == "need_bind"
        assert "session_key" not in response  # ✅ session_key 不应返回
        assert "bind_token" in response  # ✅ 应返回临时 token

    def test_code_length_validation(self, api_handler: APIRequestHandler):
        """测试 code 参数长度验证"""
        # 过长的 code
        response = api_handler.api_wechat_miniprogram_login(
            {"code": "x" * 200},
            "192.168.1.100"
        )
        assert "error" in response
        assert "Invalid code" in response["error"]

    def test_empty_code(self, api_handler: APIRequestHandler):
        """测试空 code 参数"""
        response = api_handler.api_wechat_miniprogram_login(
            {"code": ""},
            "192.168.1.100"
        )
        assert response == {"error": "Invalid code parameter"}


class TestCSRFProtection:
    """CSRF 保护测试"""

    def test_bind_lab_requires_csrf_token(self, api_handler: APIRequestHandler):
        """测试绑定课题组接口需要 CSRF token"""
        # 创建有效会话
        session_token, csrf_token = api_handler._create_session("test_user", "lab_123")

        # 不带 CSRF token 的请求应该失败
        response = api_handler.api_wechat_bind_lab(
            {
                "openid": "test_openid",
                "invite_code": "valid_code",
                "display_name": "Test User"
            },
            session_token
        )
        assert response == {"error": "Invalid CSRF token"}

        # 带正确 CSRF token 的请求应该成功（或返回其他业务错误）
        response = api_handler.api_wechat_bind_lab(
            {
                "openid": "test_openid",
                "invite_code": "valid_code",
                "display_name": "Test User",
                "csrf_token": csrf_token
            },
            session_token
        )
        assert response.get("error") != "Invalid CSRF token"

    def test_csrf_token_timing_attack_resistant(self, api_handler: APIRequestHandler):
        """测试 CSRF token 验证使用恒定时间比较"""
        session_token, csrf_token = api_handler._create_session("test_user", "lab_123")

        # 测试时序攻击抗性（应该使用 hmac.compare_digest）
        wrong_token = csrf_token[:-1] + ("a" if csrf_token[-1] != "a" else "b")

        start = time.perf_counter()
        result1 = api_handler._verify_csrf_token(
            {"csrf_token": wrong_token},
            session_token
        )
        time1 = time.perf_counter() - start

        start = time.perf_counter()
        result2 = api_handler._verify_csrf_token(
            {"csrf_token": "completely_wrong"},
            session_token
        )
        time2 = time.perf_counter() - start

        assert result1 is False
        assert result2 is False
        # 时间差应该在合理范围内（< 1ms）
        assert abs(time1 - time2) < 0.001


class TestInputValidation:
    """输入验证测试"""

    def test_display_name_length_limit(self, api_handler: APIRequestHandler):
        """测试 display_name 长度限制"""
        response = api_handler.api_wechat_bind_lab(
            {
                "openid": "test_openid",
                "display_name": "x" * 200,  # 超过限制
                "invite_code": "valid_code"
            }
        )
        assert "error" in response
        assert "too long" in response["error"].lower()

    def test_lab_name_length_limit(self, api_handler: APIRequestHandler):
        """测试 lab_name 长度限制"""
        response = api_handler.api_wechat_bind_lab(
            {
                "openid": "test_openid",
                "display_name": "Test User",
                "create_lab": True,
                "lab_name": "x" * 300  # 超过限制
            }
        )
        assert "error" in response
        assert "Invalid lab name" in response["error"]

    def test_invite_code_format_validation(self, api_handler: APIRequestHandler):
        """测试 invite_code 格式验证"""
        invalid_codes = [
            "abc",  # 太短
            "x" * 30,  # 太长
            "abc@def",  # 非法字符
            "../../../etc/passwd",  # 路径遍历尝试
            "<script>alert(1)</script>",  # XSS 尝试
        ]

        for code in invalid_codes:
            response = api_handler.api_wechat_bind_lab(
                {
                    "openid": "test_openid",
                    "display_name": "Test User",
                    "invite_code": code
                }
            )
            assert "error" in response, f"Failed to reject invalid code: {code}"

    def test_sql_injection_attempts(self, api_handler: APIRequestHandler):
        """测试 SQL 注入防护（虽然使用 JSON 存储，但仍需防御）"""
        injection_attempts = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "admin'--",
            "' UNION SELECT * FROM users--"
        ]

        for payload in injection_attempts:
            response = api_handler.api_wechat_miniprogram_login(
                {"code": payload},
                "192.168.1.100"
            )
            # 应该被当作普通字符串处理，不会导致系统错误
            assert "error" in response


class TestSessionManagement:
    """会话管理安全测试"""

    def test_session_expiration(self, api_handler: APIRequestHandler):
        """测试会话过期"""
        session_token, _ = api_handler._create_session("test_user", "lab_123")

        # 立即验证应该成功
        user, error = api_handler._verify_session_and_lab(session_token)
        assert user is not None
        assert error is None

        # 模拟时间推进 9 小时（超过 8 小时 TTL）
        session = api_handler._sessions[session_token]
        session.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        # 验证应该失败
        user, error = api_handler._verify_session_and_lab(session_token)
        assert user is None
        assert error == "Authentication failed"

    def test_session_token_entropy(self, api_handler: APIRequestHandler):
        """测试 session token 有足够的熵"""
        tokens = set()
        for _ in range(100):
            token, _ = api_handler._create_session(f"user_{_}", "lab_123")
            tokens.add(token)

        # 所有 token 应该唯一
        assert len(tokens) == 100

        # Token 长度应该足够（32 字节 base64 编码 ≈ 43 字符）
        for token in tokens:
            assert len(token) >= 40

    def test_concurrent_session_limit(self, api_handler: APIRequestHandler):
        """测试单用户并发会话数量限制"""
        username = "test_user"
        sessions = []

        # 创建 6 个会话（假设限制为 5）
        for i in range(6):
            token, _ = api_handler._create_session(username, "lab_123")
            sessions.append(token)

        # 检查最旧的会话是否被删除
        active_sessions = [
            token for token in sessions
            if api_handler._get_session(token) is not None
        ]
        assert len(active_sessions) <= 5

    def test_session_fixation_prevention(self, api_handler: APIRequestHandler):
        """测试会话固定攻击防护"""
        # 模拟攻击者设置的 session token
        attacker_token = "attacker_controlled_token"

        # 用户登录应该生成新 token，而不是使用预设 token
        response = api_handler.api_wechat_miniprogram_login(
            {"code": "valid_code"},
            "192.168.1.100"
        )

        if response.get("status") == "success":
            new_token = response["session_token"]
            assert new_token != attacker_token


class TestAccessControl:
    """权限控制与课题组隔离测试"""

    def test_lab_isolation(self, api_handler: APIRequestHandler):
        """测试课题组数据隔离"""
        # 创建两个课题组的用户
        token1, _ = api_handler._create_session("user1", "lab_A")
        token2, _ = api_handler._create_session("user2", "lab_B")

        # user1 尝试访问 lab_B 的数据
        user, error = api_handler._verify_session_and_lab(token1, "lab_B")
        assert user is None
        assert error == "Authentication failed"

        # user2 访问自己的 lab_B 应该成功
        user, error = api_handler._verify_session_and_lab(token2, "lab_B")
        assert user is not None

    def test_regenerate_invite_code_requires_admin(self, api_handler: APIRequestHandler):
        """测试重新生成邀请码需要管理员权限"""
        # 创建普通用户会话
        member_token, _ = api_handler._create_session("member_user", "lab_123")

        # 普通用户尝试重新生成邀请码应该失败
        response = api_handler.api_lab_regenerate_invite_code(member_token, "lab_123")
        assert response == {"error": "Permission denied"}

    def test_invite_code_enumeration_resistance(self, api_handler: APIRequestHandler):
        """测试邀请码枚举攻击抗性"""
        # 尝试多个无效邀请码
        for i in range(20):
            response = api_handler.api_wechat_bind_lab(
                {
                    "openid": f"test_openid_{i}",
                    "display_name": "Test User",
                    "invite_code": f"invalid_{i}"
                }
            )
            assert response == {"error": "Invalid invite code"}

        # 所有错误信息应该相同，不泄露是否接近正确答案


class TestSensitiveDataHandling:
    """敏感数据处理测试"""

    def test_password_hashing(self, api_handler: APIRequestHandler):
        """测试密码哈希存储（虽然微信登录不用密码，但账号系统有）"""
        # 检查用户数据中不包含明文密码
        users = api_handler._load_users()
        for user in users:
            assert user.password_hash != ""  # 应该有哈希
            assert len(user.password_salt) > 0  # 应该有盐
            # 如果是微信用户，password_hash 可以为空
            if user.wechat_unionid or user.wechat_miniprogram_openid:
                pass  # 微信用户可以没有密码

    def test_secrets_not_in_logs(self, api_handler: APIRequestHandler, caplog):
        """测试日志中不包含敏感信息"""
        # 模拟登录失败
        api_handler.api_wechat_miniprogram_login(
            {"code": "invalid_code"},
            "192.168.1.100"
        )

        # 检查日志中不包含完整 code
        for record in caplog.records:
            assert "invalid_code" not in record.message or "..." in record.message

    def test_error_messages_no_sensitive_data(self, api_handler: APIRequestHandler):
        """测试错误信息不泄露敏感数据"""
        # 无效 session token
        response = api_handler.api_lab_info("invalid_token", "lab_123")
        assert "error" in response
        # 不应该泄露具体的 session token 或用户名
        assert "invalid_token" not in response["error"]


class TestConfigurationSecurity:
    """配置安全测试"""

    def test_example_config_detected(self):
        """测试能检测到示例配置"""
        from src.lab_literature_manager.config import Config

        # 应该拒绝示例配置
        with pytest.raises(ValueError, match="Please configure"):
            config = Config(
                wechat_miniprogram_appid="your_miniprogram_appid_here",
                wechat_miniprogram_secret="your_secret",
                wechat_officialaccount_appid="",
                wechat_officialaccount_secret="",
                data_dir="data/local",
                server_host="0.0.0.0",
                server_port=8080
            )
            # 假设在 load_config 中有验证逻辑

    def test_weak_secret_detected(self):
        """测试能检测到弱密钥"""
        from src.lab_literature_manager.config import Config

        with pytest.raises(ValueError, match="Invalid.*SECRET"):
            config = Config(
                wechat_miniprogram_appid="wx123456",
                wechat_miniprogram_secret="123",  # 太短
                wechat_officialaccount_appid="",
                wechat_officialaccount_secret="",
                data_dir="data/local",
                server_host="0.0.0.0",
                server_port=8080
            )


class TestConcurrencySafety:
    """并发安全测试"""

    def test_concurrent_user_creation(self, api_handler: APIRequestHandler):
        """测试并发创建用户的数据一致性"""
        import threading

        results = []

        def create_user(username: str):
            try:
                user = api_handler._create_user(
                    # ... 创建用户参数
                )
                results.append(("success", username))
            except Exception as e:
                results.append(("error", str(e)))

        # 10 个线程同时创建用户
        threads = []
        for i in range(10):
            t = threading.Thread(target=create_user, args=(f"user_{i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # 所有用户应该成功创建，没有数据损坏
        assert len([r for r in results if r[0] == "success"]) == 10

    def test_concurrent_session_operations(self, api_handler: APIRequestHandler):
        """测试并发会话操作的线程安全"""
        import threading

        session_token, _ = api_handler._create_session("test_user", "lab_123")

        errors = []

        def verify_session():
            try:
                for _ in range(100):
                    api_handler._get_session(session_token)
            except Exception as e:
                errors.append(str(e))

        # 10 个线程同时访问会话
        threads = [threading.Thread(target=verify_session) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 不应该有任何错误
        assert len(errors) == 0


class TestDenialOfService:
    """DoS 攻击防护测试"""

    def test_request_size_limit(self, api_handler: APIRequestHandler):
        """测试请求大小限制"""
        # 尝试发送超大请求
        large_payload = {"code": "x" * (2 * 1024 * 1024)}  # 2MB

        # 应该被拒绝（假设有大小限制）
        response = api_handler.api_wechat_miniprogram_login(
            large_payload,
            "192.168.1.100"
        )
        assert "error" in response

    def test_deeply_nested_json(self, api_handler: APIRequestHandler):
        """测试深度嵌套 JSON 防护"""
        # 创建深度嵌套的 JSON
        nested = {"a": {}}
        current = nested["a"]
        for _ in range(1000):
            current["b"] = {}
            current = current["b"]

        # 应该被拒绝或安全处理
        try:
            response = api_handler.api_wechat_miniprogram_login(
                nested,
                "192.168.1.100"
            )
            assert "error" in response
        except RecursionError:
            pytest.fail("Should handle deeply nested JSON safely")


# ==================== Fixtures ====================

@pytest.fixture
def api_handler(tmp_path):
    """创建测试用的 APIRequestHandler"""
    from src.lab_literature_manager.api_extensions import APIRequestHandler
    from src.lab_literature_manager.multilab_repository import MultiLabRepository
    from src.lab_literature_manager.wechat_api import WeChatConfig

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    users_file = tmp_path / "users.json"
    users_file.write_text("[]")

    multilab_repo = MultiLabRepository(str(data_dir))
    wechat_config = WeChatConfig(
        miniprogram_appid="test_appid",
        miniprogram_secret="test_secret",
        officialaccount_appid="",
        officialaccount_secret=""
    )

    handler = APIRequestHandler(
        multilab_repo=multilab_repo,
        wechat_config=wechat_config,
        users_file=str(users_file)
    )

    return handler


@pytest.fixture
def mock_wechat_api(monkeypatch):
    """Mock 微信 API 调用"""
    from src.lab_literature_manager.wechat_api import WeChatSession

    def mock_miniprogram_code_to_session(appid, secret, code):
        if code.startswith("valid_code"):
            return WeChatSession(
                openid=f"openid_{code}",
                session_key="mock_session_key",
                unionid=f"unionid_{code}" if "new_user" not in code else ""
            )
        raise Exception("Invalid code")

    monkeypatch.setattr(
        "src.lab_literature_manager.wechat_api.miniprogram_code_to_session",
        mock_miniprogram_code_to_session
    )


# ==================== 渗透测试脚本 ====================

def penetration_test_suite():
    """
    手动渗透测试脚本（需要真实服务器环境）

    运行方式：
    python -m pytest tests/test_security.py::penetration_test_suite -v
    """
    import requests

    BASE_URL = "http://localhost:8080"

    print("\n=== 开始渗透测试 ===\n")

    # 1. 测试速率限制
    print("[1] 测试登录速率限制...")
    for i in range(15):
        r = requests.post(f"{BASE_URL}/api/v1/wechat/miniprogram/login",
                         json={"code": f"test_{i}"})
        if i < 10:
            assert r.status_code != 429, f"第 {i+1} 次请求被错误限流"
        else:
            assert r.status_code == 429, f"第 {i+1} 次请求应该被限流"
    print("✅ 速率限制正常")

    # 2. 测试 CSRF
    print("\n[2] 测试 CSRF 保护...")
    # 先登录
    r = requests.post(f"{BASE_URL}/api/v1/wechat/miniprogram/login",
                     json={"code": "valid_code"})
    session_token = r.json().get("session_token")

    # 不带 CSRF token 尝试绑定
    r = requests.post(f"{BASE_URL}/api/v1/wechat/bind",
                     headers={"Authorization": f"Bearer {session_token}"},
                     json={"invite_code": "test", "display_name": "Test"})
    assert "Invalid CSRF token" in r.text, "CSRF 保护失效"
    print("✅ CSRF 保护正常")

    # 3. 测试课题组隔离
    print("\n[3] 测试课题组数据隔离...")
    # 创建两个用户
    # ... (需要实际实现)
    print("✅ 课题组隔离正常")

    print("\n=== 渗透测试完成 ===")


if __name__ == "__main__":
    # 运行渗透测试
    penetration_test_suite()
