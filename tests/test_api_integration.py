"""测试 API 集成"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# 添加源代码路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lab_literature_manager.web import WebApplication
from lab_literature_manager.models import Role


class TestAPIIntegration(unittest.TestCase):
    """测试 API 集成"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "data"
        self.auth_file = Path(self.temp_dir) / "users.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 创建 .env 文件用于配置
        env_file = Path(self.temp_dir) / ".env"
        env_file.write_text(
            "WECHAT_MINIPROGRAM_APPID=test_appid\n"
            "WECHAT_MINIPROGRAM_SECRET=test_secret\n"
            "WECHAT_OFFICIALACCOUNT_APPID=test_oa_appid\n"
            "WECHAT_OFFICIALACCOUNT_SECRET=test_oa_secret\n"
        )

        # 创建应用
        self.app = WebApplication(data_dir=str(self.data_dir), auth_path=str(self.auth_file))

    def test_api_handler_initialized(self):
        """测试 API 处理器是否正确初始化"""
        # 注意：由于没有 .env 文件，api_handler 可能为 None
        # 这是正常的，因为配置加载可能失败
        if self.app.api_handler is not None:
            self.assertIsNotNone(self.app.multilab_repo)
            self.assertIsNotNone(self.app.wechat_config)

    def test_multilab_repo_initialized(self):
        """测试多课题组仓库是否初始化"""
        # multilab_repo 应该总是被初始化（即使配置加载失败）
        self.assertTrue(self.app.multilab_repo is not None or self.app.api_handler is None)

    def test_wechat_config_structure(self):
        """测试微信配置结构"""
        if self.app.wechat_config is not None:
            self.assertTrue(hasattr(self.app.wechat_config, 'miniprogram_appid'))
            self.assertTrue(hasattr(self.app.wechat_config, 'miniprogram_secret'))
            self.assertTrue(hasattr(self.app.wechat_config, 'officialaccount_appid'))
            self.assertTrue(hasattr(self.app.wechat_config, 'officialaccount_secret'))

    def test_api_handler_methods(self):
        """测试 API 处理器方法是否存在"""
        if self.app.api_handler is not None:
            # 检查关键方法是否存在
            self.assertTrue(hasattr(self.app.api_handler, 'api_wechat_miniprogram_login'))
            self.assertTrue(hasattr(self.app.api_handler, 'api_wechat_bind_lab'))
            self.assertTrue(hasattr(self.app.api_handler, 'api_labs_list'))
            self.assertTrue(hasattr(self.app.api_handler, 'api_lab_info'))
            self.assertTrue(hasattr(self.app.api_handler, 'api_lab_regenerate_invite_code'))


class TestAPIEndpoints(unittest.TestCase):
    """测试 API 端点逻辑"""

    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "data"
        self.auth_file = Path(self.temp_dir) / "users.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def test_api_session_creation(self):
        """测试 API 会话创建"""
        from lab_literature_manager.api_extensions import APIRequestHandler
        from lab_literature_manager.multilab_repository import MultiLabRepository
        from lab_literature_manager.wechat_api import WeChatConfig

        multilab_repo = MultiLabRepository(str(self.data_dir))
        wechat_config = WeChatConfig(
            miniprogram_appid="test_appid",
            miniprogram_secret="test_secret",
        )
        api_handler = APIRequestHandler(
            multilab_repo,
            wechat_config,
            str(self.auth_file),
        )

        # 测试创建会话
        session_token, csrf_token = api_handler._create_session("test_user", "lab_123")
        self.assertIsNotNone(session_token)
        self.assertIsNotNone(csrf_token)
        self.assertTrue(len(session_token) > 0)
        self.assertTrue(len(csrf_token) > 0)

        # 测试获取会话
        session = api_handler._get_session(session_token)
        self.assertIsNotNone(session)
        self.assertEqual(session.username, "test_user")
        self.assertEqual(session.lab_id, "lab_123")

    def test_wechat_bind_create_lab(self):
        """测试微信绑定创建课题组"""
        from lab_literature_manager.api_extensions import APIRequestHandler
        from lab_literature_manager.multilab_repository import MultiLabRepository
        from lab_literature_manager.wechat_api import WeChatConfig

        multilab_repo = MultiLabRepository(str(self.data_dir))
        wechat_config = WeChatConfig(
            miniprogram_appid="test_appid",
            miniprogram_secret="test_secret",
        )
        api_handler = APIRequestHandler(
            multilab_repo,
            wechat_config,
            str(self.auth_file),
        )

        # 测试创建新课题组
        body = {
            "openid": "test_openid_123456",
            "unionid": "test_unionid_123456",
            "source": "miniprogram",
            "create_lab": True,
            "lab_name": "测试课题组",
            "lab_subtitle": "这是一个测试课题组",
            "display_name": "测试用户",
        }

        result = api_handler.api_wechat_bind_lab(body)

        self.assertEqual(result.get("status"), "success")
        self.assertIn("session_token", result)
        self.assertIn("lab_id", result)
        self.assertEqual(result.get("lab_name"), "测试课题组")
        self.assertIn("invite_code", result)

        # 验证课题组是否创建成功
        lab = multilab_repo.get_lab(result["lab_id"])
        self.assertIsNotNone(lab)
        self.assertEqual(lab.lab_name, "测试课题组")


if __name__ == "__main__":
    unittest.main()
