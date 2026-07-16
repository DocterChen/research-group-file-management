"""Multi-lab repository for managing multiple research groups with data isolation."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Dict, List, Optional

from .models import Lab
from .repository import ResearchRepository


class MultiLabRepository:
    """
    管理多个课题组的数据访问，实现数据隔离。

    每个课题组拥有独立的数据目录和 ResearchRepository 实例。
    """

    def __init__(self, base_dir: str | Path):
        """
        初始化多课题组仓库。

        :param base_dir: 基础数据目录，默认为 data/local/
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.labs_file = self.base_dir / "labs.json"
        self._lab_repos: Dict[str, ResearchRepository] = {}
        self._labs_cache: Optional[Dict[str, Lab]] = None

    def _load_labs(self) -> Dict[str, Lab]:
        """加载所有课题组信息"""
        if not self.labs_file.exists():
            return {}

        with open(self.labs_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        return {
            lab_id: Lab.from_dict(lab_data)
            for lab_id, lab_data in data.items()
        }

    def _save_labs(self, labs: Dict[str, Lab]) -> None:
        """保存课题组信息（原子替换）"""
        temp_file = self.labs_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            data = {lab_id: lab.to_dict() for lab_id, lab in labs.items()}
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp_file.replace(self.labs_file)
        self._labs_cache = labs

    def list_labs(self) -> List[Lab]:
        """列出所有课题组"""
        if self._labs_cache is None:
            self._labs_cache = self._load_labs()
        return list(self._labs_cache.values())

    def get_lab(self, lab_id: str) -> Optional[Lab]:
        """获取指定课题组信息"""
        if self._labs_cache is None:
            self._labs_cache = self._load_labs()
        return self._labs_cache.get(lab_id)

    def create_lab(
        self,
        lab_name: str,
        lab_subtitle: str = "",
        admin_username: str = "",
        generate_invite_code: bool = True,
    ) -> Lab:
        """
        创建新课题组。

        :param lab_name: 课题组名称
        :param lab_subtitle: 副标题
        :param admin_username: 初始管理员用户名
        :param generate_invite_code: 是否生成邀请码
        :return: 新创建的 Lab 对象
        """
        if self._labs_cache is None:
            self._labs_cache = self._load_labs()

        # 生成唯一 lab_id
        lab_id = f"lab_{secrets.token_urlsafe(8)}"
        while lab_id in self._labs_cache:
            lab_id = f"lab_{secrets.token_urlsafe(8)}"

        # 生成邀请码
        invite_code = secrets.token_urlsafe(6) if generate_invite_code else ""

        # 创建 Lab 对象
        admin_usernames = [admin_username] if admin_username else []
        lab = Lab(
            lab_id=lab_id,
            lab_name=lab_name,
            lab_subtitle=lab_subtitle,
            admin_usernames=admin_usernames,
            invite_code=invite_code,
        )

        # 创建课题组数据目录
        lab_dir = self.base_dir / lab_id
        lab_dir.mkdir(parents=True, exist_ok=True)

        # 初始化空数据文件（创建 ResearchRepository 会自动初始化）
        repo = ResearchRepository(str(lab_dir))
        # ResearchRepository 的 __init__ 不会自动创建文件，
        # 但访问时会自动加载或创建，所以这里只需要实例化即可

        # 保存课题组信息
        self._labs_cache[lab_id] = lab
        self._save_labs(self._labs_cache)

        return lab

    def update_lab(self, lab: Lab) -> None:
        """更新课题组信息"""
        if self._labs_cache is None:
            self._labs_cache = self._load_labs()

        if lab.lab_id not in self._labs_cache:
            raise ValueError(f"Lab {lab.lab_id} does not exist.")

        self._labs_cache[lab.lab_id] = lab
        self._save_labs(self._labs_cache)

    def delete_lab(self, lab_id: str) -> None:
        """
        删除课题组（谨慎操作，会删除所有数据）。

        :param lab_id: 课题组 ID
        """
        if self._labs_cache is None:
            self._labs_cache = self._load_labs()

        if lab_id not in self._labs_cache:
            raise ValueError(f"Lab {lab_id} does not exist.")

        # 删除课题组数据目录
        lab_dir = self.base_dir / lab_id
        if lab_dir.exists():
            import shutil
            shutil.rmtree(lab_dir)

        # 删除课题组记录
        del self._labs_cache[lab_id]
        self._save_labs(self._labs_cache)

        # 清理缓存的 repository
        if lab_id in self._lab_repos:
            del self._lab_repos[lab_id]

    def get_lab_repo(self, lab_id: str) -> ResearchRepository:
        """
        获取指定课题组的 ResearchRepository。

        :param lab_id: 课题组 ID
        :return: ResearchRepository 实例
        :raises ValueError: 如果课题组不存在
        """
        if self._labs_cache is None:
            self._labs_cache = self._load_labs()

        if lab_id not in self._labs_cache:
            raise ValueError(f"Lab {lab_id} does not exist.")

        # 缓存 repository 实例
        if lab_id not in self._lab_repos:
            lab_dir = self.base_dir / lab_id
            self._lab_repos[lab_id] = ResearchRepository(str(lab_dir))

        return self._lab_repos[lab_id]

    def find_lab_by_invite_code(self, invite_code: str) -> Optional[Lab]:
        """
        根据邀请码查找课题组。

        :param invite_code: 邀请码
        :return: Lab 对象或 None
        """
        if self._labs_cache is None:
            self._labs_cache = self._load_labs()

        for lab in self._labs_cache.values():
            if lab.invite_code and lab.invite_code == invite_code:
                return lab
        return None

    def regenerate_invite_code(self, lab_id: str) -> str:
        """
        重新生成课题组邀请码。

        :param lab_id: 课题组 ID
        :return: 新的邀请码
        """
        lab = self.get_lab(lab_id)
        if not lab:
            raise ValueError(f"Lab {lab_id} does not exist.")

        from dataclasses import replace
        new_invite_code = secrets.token_urlsafe(6)
        updated_lab = replace(lab, invite_code=new_invite_code)
        self.update_lab(updated_lab)
        return new_invite_code
