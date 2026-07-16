"""
Unit tests for multi-lab repository and WeChat API integration.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lab_literature_manager.models import Lab, Member, Project, ResearchOutput, Role
from lab_literature_manager.multilab_repository import MultiLabRepository


class TestMultiLabRepository(unittest.TestCase):
    """测试多课题组数据隔离"""

    def setUp(self):
        """创建临时目录用于测试"""
        self.test_dir = tempfile.mkdtemp()
        self.repo = MultiLabRepository(self.test_dir)

    def tearDown(self):
        """清理测试数据"""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_lab(self):
        """测试创建课题组"""
        lab = self.repo.create_lab(
            lab_name="测试课题组",
            lab_subtitle="用于单元测试",
            admin_username="admin_user",
        )

        self.assertIsNotNone(lab)
        self.assertEqual(lab.lab_name, "测试课题组")
        self.assertEqual(lab.lab_subtitle, "用于单元测试")
        self.assertIn("admin_user", lab.admin_usernames)
        self.assertTrue(lab.invite_code)  # 应该生成邀请码

        # 验证数据目录已创建
        lab_dir = Path(self.test_dir) / lab.lab_id
        self.assertTrue(lab_dir.exists())

    def test_list_labs(self):
        """测试列出所有课题组"""
        lab1 = self.repo.create_lab("课题组1", "描述1")
        lab2 = self.repo.create_lab("课题组2", "描述2")

        labs = self.repo.list_labs()
        self.assertEqual(len(labs), 2)

        lab_names = {lab.lab_name for lab in labs}
        self.assertIn("课题组1", lab_names)
        self.assertIn("课题组2", lab_names)

    def test_get_lab(self):
        """测试获取课题组信息"""
        lab = self.repo.create_lab("测试课题组")
        retrieved_lab = self.repo.get_lab(lab.lab_id)

        self.assertIsNotNone(retrieved_lab)
        self.assertEqual(retrieved_lab.lab_id, lab.lab_id)
        self.assertEqual(retrieved_lab.lab_name, "测试课题组")

    def test_update_lab(self):
        """测试更新课题组信息"""
        lab = self.repo.create_lab("原始名称")

        from dataclasses import replace
        updated_lab = replace(lab, lab_name="更新后名称", lab_subtitle="新描述")
        self.repo.update_lab(updated_lab)

        retrieved_lab = self.repo.get_lab(lab.lab_id)
        self.assertEqual(retrieved_lab.lab_name, "更新后名称")
        self.assertEqual(retrieved_lab.lab_subtitle, "新描述")

    def test_delete_lab(self):
        """测试删除课题组"""
        lab = self.repo.create_lab("待删除课题组")
        lab_id = lab.lab_id

        # 验证课题组存在
        self.assertIsNotNone(self.repo.get_lab(lab_id))

        # 删除课题组
        self.repo.delete_lab(lab_id)

        # 验证课题组已删除
        self.assertIsNone(self.repo.get_lab(lab_id))

        # 验证数据目录已删除
        lab_dir = Path(self.test_dir) / lab_id
        self.assertFalse(lab_dir.exists())

    def test_get_lab_repo(self):
        """测试获取课题组的 ResearchRepository"""
        lab = self.repo.create_lab("测试课题组")
        lab_repo = self.repo.get_lab_repo(lab.lab_id)

        self.assertIsNotNone(lab_repo)

        # 验证可以添加成员
        member = Member(
            member_id="M001",
            name="张三",
            role=Role.MEMBER,
            email="zhangsan@example.com",
        )
        lab_repo.add_member(member)

        # 验证成员已添加
        retrieved_member = lab_repo.get_member("M001")
        self.assertIsNotNone(retrieved_member)
        self.assertEqual(retrieved_member.name, "张三")

    def test_data_isolation_between_labs(self):
        """测试课题组之间的数据隔离"""
        # 创建两个课题组
        lab1 = self.repo.create_lab("课题组1")
        lab2 = self.repo.create_lab("课题组2")

        repo1 = self.repo.get_lab_repo(lab1.lab_id)
        repo2 = self.repo.get_lab_repo(lab2.lab_id)

        # 在课题组1添加成员
        member1 = Member(member_id="M001", name="成员1", role=Role.MEMBER)
        repo1.add_member(member1)

        # 在课题组2添加成员
        member2 = Member(member_id="M002", name="成员2", role=Role.MEMBER)
        repo2.add_member(member2)

        # 验证数据隔离
        self.assertIsNotNone(repo1.get_member("M001"))

        # 课题组1看不到课题组2的成员（应该抛出 KeyError）
        with self.assertRaises(KeyError):
            repo1.get_member("M002")

        self.assertIsNotNone(repo2.get_member("M002"))

        # 课题组2看不到课题组1的成员（应该抛出 KeyError）
        with self.assertRaises(KeyError):
            repo2.get_member("M001")

    def test_find_lab_by_invite_code(self):
        """测试根据邀请码查找课题组"""
        lab = self.repo.create_lab("测试课题组", generate_invite_code=True)
        invite_code = lab.invite_code

        found_lab = self.repo.find_lab_by_invite_code(invite_code)
        self.assertIsNotNone(found_lab)
        self.assertEqual(found_lab.lab_id, lab.lab_id)

        # 测试无效邀请码
        invalid_lab = self.repo.find_lab_by_invite_code("invalid_code")
        self.assertIsNone(invalid_lab)

    def test_regenerate_invite_code(self):
        """测试重新生成邀请码"""
        lab = self.repo.create_lab("测试课题组")
        old_invite_code = lab.invite_code

        new_invite_code = self.repo.regenerate_invite_code(lab.lab_id)

        self.assertNotEqual(new_invite_code, old_invite_code)

        # 验证新邀请码可用
        found_lab = self.repo.find_lab_by_invite_code(new_invite_code)
        self.assertIsNotNone(found_lab)
        self.assertEqual(found_lab.lab_id, lab.lab_id)

        # 验证旧邀请码失效
        old_lab = self.repo.find_lab_by_invite_code(old_invite_code)
        self.assertIsNone(old_lab)

    def test_labs_persistence(self):
        """测试课题组信息持久化"""
        # 创建课题组
        lab = self.repo.create_lab("持久化测试", "描述")

        # 重新加载
        new_repo = MultiLabRepository(self.test_dir)
        retrieved_lab = new_repo.get_lab(lab.lab_id)

        self.assertIsNotNone(retrieved_lab)
        self.assertEqual(retrieved_lab.lab_name, "持久化测试")
        self.assertEqual(retrieved_lab.lab_subtitle, "描述")


class TestLabModel(unittest.TestCase):
    """测试 Lab 模型"""

    def test_lab_creation(self):
        """测试创建 Lab 对象"""
        lab = Lab(
            lab_id="lab_test123",
            lab_name="测试课题组",
            lab_subtitle="测试描述",
            admin_usernames=["admin1", "admin2"],
            invite_code="ABC123",
        )

        self.assertEqual(lab.lab_id, "lab_test123")
        self.assertEqual(lab.lab_name, "测试课题组")
        self.assertEqual(lab.lab_subtitle, "测试描述")
        self.assertIn("admin1", lab.admin_usernames)
        self.assertEqual(lab.invite_code, "ABC123")

    def test_lab_validation(self):
        """测试 Lab 对象验证"""
        # lab_id 不能为空
        with self.assertRaises(ValueError):
            Lab(lab_id="", lab_name="测试")

        # lab_name 不能为空
        with self.assertRaises(ValueError):
            Lab(lab_id="lab_123", lab_name="")

    def test_lab_serialization(self):
        """测试 Lab 对象序列化"""
        lab = Lab(
            lab_id="lab_test",
            lab_name="测试课题组",
            lab_subtitle="描述",
            admin_usernames=["admin"],
            invite_code="CODE123",
            settings={"key": "value"},
        )

        # 序列化
        lab_dict = lab.to_dict()
        self.assertEqual(lab_dict["lab_id"], "lab_test")
        self.assertEqual(lab_dict["lab_name"], "测试课题组")

        # 反序列化
        lab_restored = Lab.from_dict(lab_dict)
        self.assertEqual(lab_restored.lab_id, lab.lab_id)
        self.assertEqual(lab_restored.lab_name, lab.lab_name)
        self.assertEqual(lab_restored.settings, lab.settings)


if __name__ == "__main__":
    unittest.main()
