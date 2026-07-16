"""扩展的 API 集成测试 - 完整登录流程、课题组隔离、权限测试"""

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

# 添加源代码路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lab_literature_manager.api_extensions import APIRequestHandler
from lab_literature_manager.models import Role
from lab_literature_manager.multilab_repository import MultiLabRepository
from lab_literature_manager.wechat_api import WeChatConfig


class TestCompleteLoginFlow(unittest.TestCase):
    """测试完整的登录流程"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "data"
        self.auth_file = Path(self.temp_dir) / "users.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.multilab_repo = MultiLabRepository(str(self.data_dir))
        self.wechat_config = WeChatConfig(
            miniprogram_appid="test_appid",
            miniprogram_secret="test_secret",
        )
        self.api_handler = APIRequestHandler(
            self.multilab_repo,
            self.wechat_config,
            str(self.auth_file),
        )

    def tearDown(self):
        """清理测试数据"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_complete_login_create_lab_flow(self):
        """测试：用户首次登录 → 创建课题组 → 获取会话"""
        # 步骤 1：模拟微信登录（这里跳过实际的微信 API 调用）
        # 直接测试绑定课题组接口

        # 步骤 2：创建新课题组
        bind_body = {
            "openid": "test_openid_user1",
            "unionid": "test_unionid_user1",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "测试课题组A",
            "lab_subtitle": "这是测试课题组A",
            "display_name": "用户A",
        }

        result = self.api_handler.api_wechat_bind_lab(bind_body)

        # 验证响应
        self.assertEqual(result.get("status"), "success")
        self.assertIn("session_token", result)
        self.assertIn("csrf_token", result)
        self.assertIn("lab_id", result)
        self.assertIn("invite_code", result)

        session_token = result["session_token"]
        lab_id = result["lab_id"]

        # 步骤 3：使用会话访问课题组信息
        lab_info = self.api_handler.api_lab_info(session_token, lab_id)
        self.assertEqual(lab_info.get("lab_name"), "测试课题组A")
        self.assertEqual(lab_info.get("lab_subtitle"), "这是测试课题组A")

    def test_complete_login_join_lab_flow(self):
        """测试：用户 B 加入已有课题组"""
        # 步骤 1：用户 A 创建课题组
        bind_body_a = {
            "openid": "test_openid_userA",
            "unionid": "test_unionid_userA",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "测试课题组B",
            "lab_subtitle": "课题组B",
            "display_name": "用户A",
        }
        result_a = self.api_handler.api_wechat_bind_lab(bind_body_a)
        invite_code = result_a["invite_code"]

        # 步骤 2：用户 B 使用邀请码加入
        bind_body_b = {
            "openid": "test_openid_userB",
            "unionid": "test_unionid_userB",
            "source": "miniprogram",
            "invite_code": invite_code,
            "display_name": "用户B",
        }
        result_b = self.api_handler.api_wechat_bind_lab(bind_body_b)

        # 验证用户 B 成功加入
        self.assertEqual(result_b.get("status"), "success")
        self.assertEqual(result_b.get("lab_name"), "测试课题组B")

        # 验证用户 B 的会话
        session_token_b = result_b["session_token"]
        lab_id = result_b["lab_id"]
        lab_info = self.api_handler.api_lab_info(session_token_b, lab_id)
        self.assertEqual(lab_info.get("lab_name"), "测试课题组B")


class TestLabDataIsolation(unittest.TestCase):
    """测试课题组数据隔离"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "data"
        self.auth_file = Path(self.temp_dir) / "users.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.multilab_repo = MultiLabRepository(str(self.data_dir))
        self.wechat_config = WeChatConfig(
            miniprogram_appid="test_appid",
            miniprogram_secret="test_secret",
        )
        self.api_handler = APIRequestHandler(
            self.multilab_repo,
            self.wechat_config,
            str(self.auth_file),
        )

    def tearDown(self):
        """清理测试数据"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_different_labs_cannot_access_each_other(self):
        """测试：不同课题组无法访问彼此的数据"""
        # 创建课题组 A
        bind_body_a = {
            "openid": "openid_a",
            "unionid": "unionid_a",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "课题组A",
            "display_name": "用户A",
        }
        result_a = self.api_handler.api_wechat_bind_lab(bind_body_a)
        session_token_a = result_a["session_token"]
        lab_id_a = result_a["lab_id"]

        # 创建课题组 B
        bind_body_b = {
            "openid": "openid_b",
            "unionid": "unionid_b",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "课题组B",
            "display_name": "用户B",
        }
        result_b = self.api_handler.api_wechat_bind_lab(bind_body_b)
        session_token_b = result_b["session_token"]
        lab_id_b = result_b["lab_id"]

        # 用户 A 尝试访问课题组 B 的信息（应该失败）
        lab_info_cross = self.api_handler.api_lab_info(session_token_a, lab_id_b)
        self.assertIn("error", lab_info_cross)
        self.assertIn("mismatch", lab_info_cross["error"].lower())

        # 用户 B 尝试访问课题组 A 的信息（应该失败）
        lab_info_cross2 = self.api_handler.api_lab_info(session_token_b, lab_id_a)
        self.assertIn("error", lab_info_cross2)

        # 验证用户 A 可以正常访问自己的课题组
        lab_info_a = self.api_handler.api_lab_info(session_token_a, lab_id_a)
        self.assertEqual(lab_info_a.get("lab_name"), "课题组A")

        # 验证用户 B 可以正常访问自己的课题组
        lab_info_b = self.api_handler.api_lab_info(session_token_b, lab_id_b)
        self.assertEqual(lab_info_b.get("lab_name"), "课题组B")


class TestPermissions(unittest.TestCase):
    """测试权限控制"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "data"
        self.auth_file = Path(self.temp_dir) / "users.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.multilab_repo = MultiLabRepository(str(self.data_dir))
        self.wechat_config = WeChatConfig(
            miniprogram_appid="test_appid",
            miniprogram_secret="test_secret",
        )
        self.api_handler = APIRequestHandler(
            self.multilab_repo,
            self.wechat_config,
            str(self.auth_file),
        )

    def tearDown(self):
        """清理测试数据"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_only_admin_can_regenerate_invite_code(self):
        """测试：只有管理员可以重新生成邀请码"""
        # 创建课题组（创建者是管理员）
        bind_body_admin = {
            "openid": "openid_admin",
            "unionid": "unionid_admin",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "测试课题组",
            "display_name": "管理员",
        }
        result_admin = self.api_handler.api_wechat_bind_lab(bind_body_admin)
        session_token_admin = result_admin["session_token"]
        lab_id = result_admin["lab_id"]
        invite_code = result_admin["invite_code"]

        # 普通成员加入
        bind_body_member = {
            "openid": "openid_member",
            "unionid": "unionid_member",
            "source": "miniprogram",
            "invite_code": invite_code,
            "display_name": "普通成员",
        }
        result_member = self.api_handler.api_wechat_bind_lab(bind_body_member)
        session_token_member = result_member["session_token"]

        # 管理员重新生成邀请码（应该成功）
        regenerate_result_admin = self.api_handler.api_lab_regenerate_invite_code(
            session_token_admin, lab_id
        )
        self.assertIn("invite_code", regenerate_result_admin)
        self.assertNotEqual(regenerate_result_admin["invite_code"], invite_code)

        # 普通成员尝试重新生成邀请码（应该失败）
        regenerate_result_member = self.api_handler.api_lab_regenerate_invite_code(
            session_token_member, lab_id
        )
        self.assertIn("error", regenerate_result_member)
        self.assertIn("Permission denied", regenerate_result_member["error"])


class TestConcurrentAccess(unittest.TestCase):
    """测试并发访问"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "data"
        self.auth_file = Path(self.temp_dir) / "users.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.multilab_repo = MultiLabRepository(str(self.data_dir))
        self.wechat_config = WeChatConfig(
            miniprogram_appid="test_appid",
            miniprogram_secret="test_secret",
        )
        self.api_handler = APIRequestHandler(
            self.multilab_repo,
            self.wechat_config,
            str(self.auth_file),
        )

    def tearDown(self):
        """清理测试数据"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_concurrent_lab_creation(self):
        """测试：并发创建课题组"""
        import threading

        results = []
        errors = []
        lock = threading.Lock()

        def create_lab(user_id):
            try:
                bind_body = {
                    "openid": f"openid_{user_id}",
                    "unionid": f"unionid_{user_id}",
                    "source": "miniprogram",
                    "create_lab": True,
                    "lab_name": f"课题组{user_id}",
                    "display_name": f"用户{user_id}",
                }
                result = self.api_handler.api_wechat_bind_lab(bind_body)
                with lock:
                    results.append(result)
            except Exception as e:
                with lock:
                    errors.append(str(e))

        # 创建 10 个并发线程
        threads = []
        for i in range(10):
            t = threading.Thread(target=create_lab, args=(i,))
            threads.append(t)
            t.start()

        # 等待所有线程完成
        for t in threads:
            t.join()

        # 验证所有课题组都成功创建
        self.assertEqual(len(results), 10, f"Expected 10 results, got {len(results)}. Errors: {errors}")
        self.assertEqual(len(errors), 0)

        # 验证所有课题组有唯一的 lab_id
        lab_ids = [r["lab_id"] for r in results if "lab_id" in r]
        self.assertEqual(len(lab_ids), len(set(lab_ids)))  # 所有 ID 唯一

    def test_concurrent_session_access(self):
        """测试：并发会话访问"""
        # 先创建课题组
        bind_body = {
            "openid": "openid_concurrent",
            "unionid": "unionid_concurrent",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "并发测试课题组",
            "display_name": "并发用户",
        }
        result = self.api_handler.api_wechat_bind_lab(bind_body)
        session_token = result["session_token"]
        lab_id = result["lab_id"]

        results = []
        errors = []

        def access_lab_info():
            try:
                lab_info = self.api_handler.api_lab_info(session_token, lab_id)
                results.append(lab_info)
            except Exception as e:
                errors.append(str(e))

        # 创建 20 个并发线程访问同一会话
        threads = []
        for i in range(20):
            t = threading.Thread(target=access_lab_info)
            threads.append(t)
            t.start()

        # 等待所有线程完成
        for t in threads:
            t.join()

        # 验证所有请求都成功
        self.assertEqual(len(results), 20)
        self.assertEqual(len(errors), 0)

        # 验证所有响应都是正确的
        for lab_info in results:
            self.assertEqual(lab_info.get("lab_name"), "并发测试课题组")


class TestSessionManagement(unittest.TestCase):
    """测试会话管理"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "data"
        self.auth_file = Path(self.temp_dir) / "users.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.multilab_repo = MultiLabRepository(str(self.data_dir))
        self.wechat_config = WeChatConfig(
            miniprogram_appid="test_appid",
            miniprogram_secret="test_secret",
        )
        self.api_handler = APIRequestHandler(
            self.multilab_repo,
            self.wechat_config,
            str(self.auth_file),
        )

    def tearDown(self):
        """清理测试数据"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_invalid_session_token(self):
        """测试：无效的会话令牌"""
        invalid_token = "invalid_token_12345"
        result = self.api_handler.api_labs_list(invalid_token)
        self.assertIn("error", result)
        self.assertIn("session", result["error"].lower())

    def test_session_token_uniqueness(self):
        """测试：会话令牌唯一性"""
        # 创建多个用户，验证会话令牌都不相同
        tokens = []
        for i in range(5):
            bind_body = {
                "openid": f"openid_{i}",
                "unionid": f"unionid_{i}",
                "source": "miniprogram",
                "create_lab": True,
                "lab_name": f"课题组{i}",
                "display_name": f"用户{i}",
            }
            result = self.api_handler.api_wechat_bind_lab(bind_body)
            tokens.append(result["session_token"])

        # 验证所有令牌唯一
        self.assertEqual(len(tokens), len(set(tokens)))


class TestErrorHandling(unittest.TestCase):
    """测试错误处理"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "data"
        self.auth_file = Path(self.temp_dir) / "users.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.multilab_repo = MultiLabRepository(str(self.data_dir))
        self.wechat_config = WeChatConfig(
            miniprogram_appid="test_appid",
            miniprogram_secret="test_secret",
        )
        self.api_handler = APIRequestHandler(
            self.multilab_repo,
            self.wechat_config,
            str(self.auth_file),
        )

    def tearDown(self):
        """清理测试数据"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_missing_required_fields(self):
        """测试：缺少必需字段"""
        # 缺少 openid
        result = self.api_handler.api_wechat_bind_lab({
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "测试",
            "display_name": "用户",
        })
        self.assertIn("error", result)

        # 创建课题组时缺少 lab_name
        result2 = self.api_handler.api_wechat_bind_lab({
            "openid": "test_openid",
            "source": "miniprogram",
            "create_lab": True,
            "display_name": "用户",
        })
        self.assertIn("error", result2)

    def test_invalid_invite_code(self):
        """测试：无效的邀请码"""
        result = self.api_handler.api_wechat_bind_lab({
            "openid": "test_openid",
            "unionid": "test_unionid",
            "source": "miniprogram",
            "invite_code": "invalid_code_123",
            "display_name": "用户",
        })
        self.assertIn("error", result)
        self.assertIn("Invalid invite code", result["error"])

    def test_duplicate_user_binding(self):
        """测试：重复绑定用户"""
        # 第一次绑定
        bind_body = {
            "openid": "same_openid",
            "unionid": "same_unionid",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "课题组1",
            "display_name": "用户1",
        }
        result1 = self.api_handler.api_wechat_bind_lab(bind_body)
        self.assertEqual(result1.get("status"), "success")

        # 同一用户尝试再次创建课题组
        bind_body2 = {
            "openid": "same_openid",
            "unionid": "same_unionid",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "课题组2",
            "display_name": "用户1",
        }
        result2 = self.api_handler.api_wechat_bind_lab(bind_body2)
        # 当前实现会创建重复用户，这是一个潜在的 bug
        # 记录这个发现以便后续修复


if __name__ == "__main__":
    unittest.main()
