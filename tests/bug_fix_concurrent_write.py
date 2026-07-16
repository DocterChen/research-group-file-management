"""
修复并发写入竞态条件的补丁

Bug ID: BUG-001
严重程度: 高
问题: 多个线程同时写入时，原子文件替换机制存在竞态条件

修复方案:
1. 添加文件锁机制保护并发写入
2. 使用进程级锁（适用于多进程场景）
3. 添加重试机制

使用方法:
1. 安装依赖: pip install filelock
2. 应用补丁到 multilab_repository.py 和 api_extensions.py
"""

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Dict

try:
    from filelock import FileLock
    HAS_FILELOCK = True
except ImportError:
    HAS_FILELOCK = False
    import time


class SafeFileWriter:
    """安全的文件写入器，支持并发场景"""

    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        self.lock_path = self.file_path.with_suffix('.lock')

    @contextmanager
    def atomic_write(self, max_retries=3):
        """
        原子写入上下文管理器，支持文件锁和重试

        使用方式:
        with writer.atomic_write() as f:
            json.dump(data, f)
        """
        if HAS_FILELOCK:
            # 使用 filelock 库（推荐）
            lock = FileLock(str(self.lock_path), timeout=10)
            with lock:
                yield from self._do_atomic_write(max_retries)
        else:
            # 降级方案：简单重试
            yield from self._do_atomic_write(max_retries)

    def _do_atomic_write(self, max_retries):
        """执行原子写入"""
        temp_file = self.file_path.with_suffix('.tmp')

        for attempt in range(max_retries):
            try:
                # 打开临时文件
                f = open(temp_file, 'w', encoding='utf-8')
                yield f
                f.close()

                # 原子替换
                temp_file.replace(self.file_path)
                return

            except FileNotFoundError as e:
                if attempt < max_retries - 1:
                    # 重试前短暂等待
                    if not HAS_FILELOCK:
                        import time
                        time.sleep(0.01 * (attempt + 1))
                    continue
                else:
                    raise

            finally:
                # 清理临时文件
                if temp_file.exists():
                    try:
                        temp_file.unlink()
                    except:
                        pass


# ============================================================
# 补丁 1: MultiLabRepository
# ============================================================

def patched_save_labs(self, labs: Dict[str, "Lab"]) -> None:
    """
    安全保存课题组信息（带文件锁）

    替换 multilab_repository.py 中的 _save_labs 方法
    """
    writer = SafeFileWriter(self.labs_file)

    with writer.atomic_write() as f:
        data = {lab_id: lab.to_dict() for lab_id, lab in labs.items()}
        json.dump(data, f, ensure_ascii=False, indent=2)

    self._labs_cache = labs


# ============================================================
# 补丁 2: APIRequestHandler
# ============================================================

def patched_save_users(self, users: list) -> None:
    """
    安全保存用户信息（带文件锁）

    替换 api_extensions.py 中的 _save_users 方法
    """
    from pathlib import Path

    users_path = Path(self.users_file)
    writer = SafeFileWriter(users_path)

    with writer.atomic_write() as f:
        data = [user.to_dict() for user in users]
        json.dump(data, f, ensure_ascii=False, indent=2)

    self._users_cache = users


# ============================================================
# 测试修复效果
# ============================================================

def test_concurrent_write_fixed():
    """测试修复后的并发写入"""
    import tempfile
    import threading
    from pathlib import Path

    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    test_file = Path(temp_dir) / "test.json"

    results = []
    errors = []

    def write_data(i):
        try:
            writer = SafeFileWriter(test_file)
            with writer.atomic_write() as f:
                json.dump({"id": i, "data": f"test_{i}"}, f)
            results.append(i)
        except Exception as e:
            errors.append(str(e))

    # 并发写入测试
    threads = []
    for i in range(20):
        t = threading.Thread(target=write_data, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print(f"✓ 并发写入测试: {len(results)} 成功, {len(errors)} 失败")
    print(f"  成功率: {len(results) / 20 * 100:.1f}%")

    # 清理
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)

    return len(errors) == 0


if __name__ == "__main__":
    print("测试并发写入修复...")
    if test_concurrent_write_fixed():
        print("✓ 修复验证通过")
    else:
        print("✗ 修复验证失败")
