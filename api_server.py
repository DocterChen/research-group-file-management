"""
Standalone API server for WeChat integration and multi-lab support.

This script provides a lightweight HTTP API server that can run alongside
or independently from the main web.py server.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# 添加 src 目录到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from lab_literature_manager.api_extensions import APIRequestHandler
from lab_literature_manager.config import load_config
from lab_literature_manager.multilab_repository import MultiLabRepository
from lab_literature_manager.wechat_api import WeChatConfig


class APIServerHandler(BaseHTTPRequestHandler):
    """API 服务器请求处理器"""

    def _send_json_response(self, data: dict, status_code: int = 200) -> None:
        """发送 JSON 响应"""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _parse_json_body(self) -> dict:
        """解析 JSON 请求体"""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length)
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _get_session_token(self) -> str:
        """从 Authorization 头获取 session_token"""
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        return ""

    def do_OPTIONS(self) -> None:
        """处理 CORS 预检请求"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self) -> None:
        """处理 GET 请求"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        try:
            # GET /api/v1/labs - 列出课题组
            if path == "/api/v1/labs":
                session_token = self._get_session_token()
                result = self.server.api_handler.api_labs_list(session_token)
                self._send_json_response(result)
                return

            # GET /api/v1/labs/:lab_id - 获取课题组信息
            if path.startswith("/api/v1/labs/") and path.count("/") == 4:
                lab_id = path.split("/")[-1]
                session_token = self._get_session_token()
                result = self.server.api_handler.api_lab_info(session_token, lab_id)
                self._send_json_response(result)
                return

            # GET /health - 健康检查
            if path == "/health":
                self._send_json_response({"status": "ok"})
                return

            # 404
            self._send_json_response({"error": "Not found"}, 404)

        except Exception as e:
            self._send_json_response({"error": str(e)}, 500)

    def do_POST(self) -> None:
        """处理 POST 请求"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        try:
            body = self._parse_json_body()

            # POST /api/v1/wechat/miniprogram/login - 小程序登录
            if path == "/api/v1/wechat/miniprogram/login":
                result = self.server.api_handler.api_wechat_miniprogram_login(body)
                self._send_json_response(result)
                return

            # POST /api/v1/wechat/bind - 绑定课题组
            if path == "/api/v1/wechat/bind":
                result = self.server.api_handler.api_wechat_bind_lab(body)
                self._send_json_response(result)
                return

            # POST /api/v1/labs/:lab_id/regenerate_invite_code - 重新生成邀请码
            if path.endswith("/regenerate_invite_code"):
                lab_id = path.split("/")[-2]
                session_token = self._get_session_token()
                result = self.server.api_handler.api_lab_regenerate_invite_code(
                    session_token, lab_id
                )
                self._send_json_response(result)
                return

            # 404
            self._send_json_response({"error": "Not found"}, 404)

        except Exception as e:
            self._send_json_response({"error": str(e)}, 500)

    def log_message(self, format, *args):
        """自定义日志格式"""
        print(f"[API] {self.address_string()} - {format % args}")


class APIServer(ThreadingHTTPServer):
    """API 服务器"""

    def __init__(self, server_address, handler_class, api_handler):
        super().__init__(server_address, handler_class)
        self.api_handler = api_handler


def main():
    """启动 API 服务器"""
    # 加载配置
    config = load_config()

    # 初始化多课题组仓库
    multilab_repo = MultiLabRepository(config.data_dir)

    # 初始化微信配置
    wechat_config = WeChatConfig(
        miniprogram_appid=config.wechat_miniprogram_appid,
        miniprogram_secret=config.wechat_miniprogram_secret,
        officialaccount_appid=config.wechat_officialaccount_appid,
        officialaccount_secret=config.wechat_officialaccount_secret,
    )

    # 初始化 API 处理器
    users_file = str(Path(config.data_dir) / "users.json")
    api_handler = APIRequestHandler(multilab_repo, wechat_config, users_file)

    # 启动服务器
    server_address = (config.server_host, config.server_port)
    httpd = APIServer(server_address, APIServerHandler, api_handler)

    print(f"🚀 API Server started at http://{config.server_host}:{config.server_port}")
    print(f"📁 Data directory: {config.data_dir}")
    print(f"🔑 WeChat MiniProgram AppID: {config.wechat_miniprogram_appid or '(not configured)'}")
    print(f"🔑 WeChat OfficialAccount AppID: {config.wechat_officialaccount_appid or '(not configured)'}")
    print("\nAvailable endpoints:")
    print("  POST /api/v1/wechat/miniprogram/login")
    print("  POST /api/v1/wechat/bind")
    print("  GET  /api/v1/labs")
    print("  GET  /api/v1/labs/:lab_id")
    print("  POST /api/v1/labs/:lab_id/regenerate_invite_code")
    print("  GET  /health")
    print("\nPress Ctrl+C to stop the server.")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n✋ Shutting down API server...")
        httpd.shutdown()
        print("✅ API server stopped.")


if __name__ == "__main__":
    main()
