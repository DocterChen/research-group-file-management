#!/usr/bin/env python3
"""
微信小程序 API 服务器示例

使用方法：
1. 确保已创建 .env 文件，包含微信配置：
   WECHAT_MINIPROGRAM_APPID=your_appid
   WECHAT_MINIPROGRAM_SECRET=your_secret
   WECHAT_OFFICIALACCOUNT_APPID=your_oa_appid
   WECHAT_OFFICIALACCOUNT_SECRET=your_oa_secret

2. 运行服务器：
   python api_server_example.py

3. API 端点：
   - POST /api/v1/wechat/miniprogram/login - 小程序登录
   - POST /api/v1/wechat/bind - 绑定课题组
   - GET /api/v1/labs - 列出课题组
   - GET /api/v1/labs/:lab_id - 获取课题组信息
   - POST /api/v1/labs/:lab_id/regenerate_invite_code - 重新生成邀请码
   - GET /api/v1/outputs - 成果列表（小程序）
   - GET /api/v1/outputs/:output_id - 成果详情（小程序）
"""

import sys
from pathlib import Path

# 添加源代码路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from lab_literature_manager.web import create_web_server


def main():
    """启动服务器"""
    # 配置
    data_dir = Path("data/local")
    auth_path = data_dir / "users.json"
    host = "0.0.0.0"
    port = 8080

    # 创建数据目录
    data_dir.mkdir(parents=True, exist_ok=True)

    # 创建服务器
    print(f"正在启动服务器...")
    print(f"数据目录: {data_dir}")
    print(f"用户文件: {auth_path}")
    print(f"监听地址: http://{host}:{port}")
    print()
    print("Web UI 端点:")
    print(f"  - http://localhost:{port}/")
    print()
    print("API 端点:")
    print(f"  - POST http://localhost:{port}/api/v1/wechat/miniprogram/login")
    print(f"  - POST http://localhost:{port}/api/v1/wechat/bind")
    print(f"  - GET  http://localhost:{port}/api/v1/labs")
    print(f"  - GET  http://localhost:{port}/api/v1/labs/:lab_id")
    print(f"  - POST http://localhost:{port}/api/v1/labs/:lab_id/regenerate_invite_code")
    print(f"  - GET  http://localhost:{port}/api/v1/outputs")
    print(f"  - GET  http://localhost:{port}/api/v1/outputs/:output_id")
    print()
    print("按 Ctrl+C 停止服务器")
    print()

    server = create_web_server(
        data_dir=data_dir,
        auth_path=auth_path,
        host=host,
        port=port,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止服务器...")
        server.shutdown()
        print("服务器已停止")


if __name__ == "__main__":
    main()
