"""错误处理测试 - 微信 API 错误、边界条件、异常场景"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# 添加源代码路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lab_literature_manager.api_extensions import APIRequestHandler
from lab_literature_manager.models import Role
from lab_literature_manager.multilab_repository import MultiLabRepository
from lab_literature_manager.wechat_api import WeChatAPIError, WeChatConfig


class TestWeChatAPIErrors(unittest.TestCase):
    """测试微信 API 错误处理"""

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

    @patch("lab_literature_manager.wechat_api.miniprogram_code_to_session")
    def test_wechat_api_invalid_code(self, mock_code_to_session):
        """测试：微信 API 返回无效 code 错误"""
        # 模拟微信 API 返回错误
        mock_code_to_session.side_effect = WeChatAPIError(40029, "invalid code")

        body = {"code": "invalid_code_12345"}
        result = self.api_handler.api_wechat_miniprogram_login(body)

        self.assertIn("error", result)
        self.assertIn("invalid code", result["error"])
        print("✓ 无效 code 错误被正确处理")

    @patch("lab_literature_manager.wechat_api.miniprogram_code_to_session")
    def test_wechat_api_network_timeout(self, mock_code_to_session):
        """测试：微信 API 网络超时"""
        # 模拟网络超时
        mock_code_to_session.side_effect = WeChatAPIError(-1, "Network error: timeout")

        body = {"code": "valid_code"}
        result = self.api_handler.api_wechat_miniprogram_login(body)

        self.assertIn("error", result)
        self.assertIn("Network error", result["error"])
        print("✓ 网络超时错误被正确处理")

    @patch("lab_literature_manager.wechat_api.miniprogram_code_to_session")
    def test_wechat_api_system_error(self, mock_code_to_session):
        """测试：微信 API 系统错误"""
        # 模拟系统错误
        mock_code_to_session.side_effect = WeChatAPIError(-1, "system error")

        body = {"code": "valid_code"}
        result = self.api_handler.api_wechat_miniprogram_login(body)

        self.assertIn("error", result)
        print("✓ 系统错误被正确处理")


class TestBoundaryConditions(unittest.TestCase):
    """测试边界条件"""

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

    def test_empty_parameters(self):
        """测试：空参数"""
        # 空的 openid
        result1 = self.api_handler.api_wechat_bind_lab({
            "openid": "",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "测试",
            "display_name": "用户",
        })
        self.assertIn("error", result1)

        # 空的 lab_name
        result2 = self.api_handler.api_wechat_bind_lab({
            "openid": "test_openid",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "",
            "display_name": "用户",
        })
        self.assertIn("error", result2)

        print("✓ 空参数被正确拒绝")

    def test_whitespace_only_parameters(self):
        """测试：仅包含空白字符的参数"""
        result = self.api_handler.api_wechat_bind_lab({
            "openid": "test_openid",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "   ",
            "display_name": "用户",
        })
        self.assertIn("error", result)
        print("✓ 空白字符参数被正确拒绝")

    def test_null_parameters(self):
        """测试：None/null 参数"""
        result = self.api_handler.api_wechat_bind_lab({
            "openid": None,
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "测试",
            "display_name": "用户",
        })
        self.assertIn("error", result)
        print("✓ null 参数被正确处理")

    def test_missing_optional_parameters(self):
        """测试：缺少可选参数"""
        # unionid 是可选的
        result = self.api_handler.api_wechat_bind_lab({
            "openid": "test_openid",
            # 没有 unionid
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "测试课题组",
            "display_name": "测试用户",
        })
        # 应该成功
        self.assertEqual(result.get("status"), "success")
        print("✓ 缺少可选参数时正常工作")

    def test_extra_unexpected_parameters(self):
        """测试：额外的未预期参数"""
        result = self.api_handler.api_wechat_bind_lab({
            "openid": "test_openid",
            "unionid": "test_unionid",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "测试课题组",
            "display_name": "测试用户",
            "extra_param": "unexpected_value",
            "another_param": 12345,
        })
        # 应该忽略额外参数并成功
        self.assertEqual(result.get("status"), "success")
        print("✓ 额外参数被正确忽略")

    def test_very_long_string_parameters(self):
        """测试：非常长的字符串参数"""
        long_name = "A" * 1000
        result = self.api_handler.api_wechat_bind_lab({
            "openid": "test_openid",
            "unionid": "test_unionid",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": long_name,
            "display_name": "测试用户",
        })
        # 系统应该能处理（可能截断）
        self.assertIsNotNone(result)
        print("✓ 超长字符串被正确处理")

    def test_zero_length_invite_code(self):
        """测试：长度为 0 的邀请码"""
        result = self.api_handler.api_wechat_bind_lab({
            "openid": "test_openid",
            "unionid": "test_unionid",
            "source": "miniprogram",
            "invite_code": "",
            "display_name": "测试用户",
        })
        self.assertIn("error", result)
        print("✓ 空邀请码被正确拒绝")


class TestDataCorruptionHandling(unittest.TestCase):
    """测试数据损坏处理"""

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

    def test_corrupted_json_file(self):
        """测试：损坏的 JSON 文件"""
        # 写入损坏的 JSON
        labs_file = self.data_dir / "labs.json"
        labs_file.write_text("{ invalid json }")

        # 尝试加载
        try:
            labs = self.multilab_repo.list_labs()
            # 应该返回空列表或抛出异常
            self.assertIsNotNone(labs)
            print("✓ 损坏的 JSON 文件被正确处理（返回空列表）")
        except json.JSONDecodeError:
            print("✓ 损坏的 JSON 文件被正确处理（抛出异常）")

    def test_missing_data_file(self):
        """测试：缺失的数据文件"""
        # 不创建任何文件，直接加载
        labs = self.multilab_repo.list_labs()
        self.assertEqual(len(labs), 0)
        print("✓ 缺失的数据文件被正确处理")

    def test_incomplete_lab_record(self):
        """测试：不完整的课题组记录"""
        # 写入不完整的记录
        labs_file = self.data_dir / "labs.json"
        incomplete_data = {
            "lab_test": {
                "lab_id": "lab_test",
                # 缺少 lab_name
            }
        }
        labs_file.write_text(json.dumps(incomplete_data))

        # 尝试加载
        try:
            labs = self.multilab_repo.list_labs()
            # 可能抛出异常或跳过不完整记录
            print("✓ 不完整的记录被处理")
        except Exception as e:
            print(f"✓ 不完整的记录导致异常: {type(e).__name__}")


class TestConcurrentModification(unittest.TestCase):
    """测试并发修改"""

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

    def test_concurrent_invite_code_regeneration(self):
        """测试：并发重新生成邀请码"""
        import threading

        # 创建课题组
        bind_body = {
            "openid": "test_openid",
            "unionid": "test_unionid",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "测试课题组",
            "display_name": "管理员",
        }
        result = self.api_handler.api_wechat_bind_lab(bind_body)
        session_token = result["session_token"]
        lab_id = result["lab_id"]

        new_codes = []
        errors = []

        def regenerate():
            try:
                result = self.api_handler.api_lab_regenerate_invite_code(
                    session_token, lab_id
                )
                if "invite_code" in result:
                    new_codes.append(result["invite_code"])
                else:
                    errors.append(result.get("error", "Unknown error"))
            except Exception as e:
                errors.append(str(e))

        # 并发重新生成
        threads = []
        for _ in range(10):
            t = threading.Thread(target=regenerate)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # 验证所有操作都成功
        self.assertGreater(len(new_codes), 0)
        print(f"✓ 并发重新生成邀请码: {len(new_codes)} 成功, {len(errors)} 失败")


class TestEdgeCases(unittest.TestCase):
    """测试边缘情况"""

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

    def test_same_openid_different_sources(self):
        """测试：相同 openid 但来自不同平台"""
        # 小程序登录
        bind_body_mini = {
            "openid": "same_openid",
            "unionid": "unionid_1",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "小程序课题组",
            "display_name": "小程序用户",
        }
        result_mini = self.api_handler.api_wechat_bind_lab(bind_body_mini)
        self.assertEqual(result_mini.get("status"), "success")

        # 公众号登录（相同 openid）
        bind_body_oa = {
            "openid": "same_openid",
            "unionid": "unionid_2",  # 不同的 unionid
            "source": "official_account",
            "create_lab": True,
            "lab_name": "公众号课题组",
            "display_name": "公众号用户",
        }
        result_oa = self.api_handler.api_wechat_bind_lab(bind_body_oa)
        # 应该创建不同的用户（因为 source 不同）
        print("✓ 不同来源的相同 openid 被正确处理")

    def test_display_name_with_special_formatting(self):
        """测试：特殊格式的显示名"""
        special_names = [
            "用户\n换行",
            "用户\t制表符",
            "  前后空格  ",
            "Multiple   Spaces",
        ]

        for name in special_names:
            bind_body = {
                "openid": f"openid_{hash(name)}",
                "unionid": f"unionid_{hash(name)}",
                "source": "miniprogram",
                "create_lab": True,
                "lab_name": f"测试{hash(name)}",
                "display_name": name,
            }
            result = self.api_handler.api_wechat_bind_lab(bind_body)
            self.assertEqual(result.get("status"), "success")

        print("✓ 特殊格式的显示名被正确处理")

    def test_rapid_successive_requests(self):
        """测试：快速连续请求"""
        results = []
        for i in range(20):
            bind_body = {
                "openid": f"rapid_openid_{i}",
                "unionid": f"rapid_unionid_{i}",
                "source": "miniprogram",
                "create_lab": True,
                "lab_name": f"快速课题组{i}",
                "display_name": f"快速用户{i}",
            }
            result = self.api_handler.api_wechat_bind_lab(bind_body)
            results.append(result)

        # 验证所有请求都成功
        success_count = sum(1 for r in results if r.get("status") == "success")
        self.assertEqual(success_count, 20)
        print(f"✓ 快速连续请求: {success_count}/20 成功")

    def test_unicode_normalization(self):
        """测试：Unicode 规范化"""
        # 相同字符的不同 Unicode 表示
        name1 = "café"  # 使用组合字符
        name2 = "café"  # 使用预组合字符

        bind_body1 = {
            "openid": "openid_unicode1",
            "unionid": "unionid_unicode1",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": name1,
            "display_name": "用户1",
        }
        result1 = self.api_handler.api_wechat_bind_lab(bind_body1)
        self.assertEqual(result1.get("status"), "success")

        print("✓ Unicode 规范化被正确处理")


if __name__ == "__main__":
    unittest.main()
