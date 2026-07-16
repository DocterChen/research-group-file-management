"""
修复并发写入竞态条件 - 使用 fcntl 文件锁

这个版本使用操作系统级别的文件锁，确保真正的互斥访问。
"""

import fcntl
import json
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path


class ConcurrentSafeFileWriter:
    """线程和进程安全的文件写入器"""

    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def write_lock(self):
        """获取写锁"""
        lock_path = self.file_path.parent / f".{self.file_path.name}.lock"
        lock_fd = open(lock_path, 'w')
        try:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            lock_fd.close()

    def safe_write_json(self, data: dict) -> None:
        """安全地写入 JSON 数据"""
        with self.write_lock():
            # 在锁保护下执行原子写入
            temp_file = self.file_path.with_suffix('.tmp')
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                temp_file.replace(self.file_path)
            finally:
                if temp_file.exists():
                    temp_file.unlink(missing_ok=True)


# ============================================================
# 测试修复效果
# ============================================================

def test_concurrent_write_with_fcntl():
    """测试使用 fcntl 的并发写入"""
    temp_dir = tempfile.mkdtemp()
    test_file = Path(temp_dir) / "test.json"

    results = []
    errors = []
    lock = threading.Lock()

    def write_data(i):
        try:
            writer = ConcurrentSafeFileWriter(test_file)
            writer.safe_write_json({"id": i, "data": f"test_{i}"})
            with lock:
                results.append(i)
        except Exception as e:
            with lock:
                errors.append(str(e))

    # 并发写入测试
    threads = []
    for i in range(50):  # 增加到 50 个线程
        t = threading.Thread(target=write_data, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    print(f"✓ 并发写入测试（50 线程）: {len(results)} 成功, {len(errors)} 失败")
    print(f"  成功率: {len(results) / 50 * 100:.1f}%")

    if errors:
        print(f"  错误示例: {errors[:3]}")

    # 清理
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)

    return len(errors) == 0


if __name__ == "__main__":
    print("=" * 60)
    print("测试并发写入修复（fcntl 文件锁）")
    print("=" * 60)

    success = test_concurrent_write_with_fcntl()

    print()
    if success:
        print("✓ 修复验证通过 - 所有并发写入成功")
    else:
        print("✗ 修复验证失败 - 仍有错误")
