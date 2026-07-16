#!/usr/bin/env python3
"""
API 测试客户端

用于测试微信小程序 API 端点
"""

import json
import requests


BASE_URL = "http://localhost:8080"


def test_api_endpoints():
    """测试 API 端点"""
    print("=" * 60)
    print("API 端点测试")
    print("=" * 60)
    print()

    # 测试 1: 微信小程序登录（模拟）
    print("1. 测试微信小程序登录 (POST /api/v1/wechat/miniprogram/login)")
    login_data = {
        "code": "test_code_12345"
    }
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/wechat/miniprogram/login",
            json=login_data,
            headers={"Content-Type": "application/json"}
        )
        print(f"   状态码: {response.status_code}")
        print(f"   响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
    except Exception as e:
        print(f"   错误: {e}")
    print()

    # 测试 2: 微信绑定课题组
    print("2. 测试微信绑定课题组 (POST /api/v1/wechat/bind)")
    bind_data = {
        "openid": "test_openid_123456",
        "unionid": "test_unionid_123456",
        "source": "miniprogram",
        "create_lab": True,
        "lab_name": "测试课题组",
        "lab_subtitle": "这是一个测试课题组",
        "display_name": "测试用户"
    }
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/wechat/bind",
            json=bind_data,
            headers={"Content-Type": "application/json"}
        )
        print(f"   状态码: {response.status_code}")
        result = response.json()
        print(f"   响应: {json.dumps(result, ensure_ascii=False, indent=2)}")

        # 保存 session_token 和 lab_id 用于后续测试
        session_token = result.get("session_token", "")
        lab_id = result.get("lab_id", "")
    except Exception as e:
        print(f"   错误: {e}")
        session_token = ""
        lab_id = ""
    print()

    # 测试 3: 列出课题组
    if session_token:
        print("3. 测试列出课题组 (GET /api/v1/labs)")
        try:
            response = requests.get(
                f"{BASE_URL}/api/v1/labs",
                headers={
                    "X-Session-Token": session_token
                }
            )
            print(f"   状态码: {response.status_code}")
            print(f"   响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
        except Exception as e:
            print(f"   错误: {e}")
        print()

    # 测试 4: 获取课题组信息
    if session_token and lab_id:
        print(f"4. 测试获取课题组信息 (GET /api/v1/labs/{lab_id})")
        try:
            response = requests.get(
                f"{BASE_URL}/api/v1/labs/{lab_id}",
                headers={
                    "X-Session-Token": session_token
                }
            )
            print(f"   状态码: {response.status_code}")
            print(f"   响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
        except Exception as e:
            print(f"   错误: {e}")
        print()

    # 测试 5: 获取成果列表
    if session_token:
        print("5. 测试获取成果列表 (GET /api/v1/outputs)")
        try:
            response = requests.get(
                f"{BASE_URL}/api/v1/outputs",
                headers={
                    "X-Session-Token": session_token
                }
            )
            print(f"   状态码: {response.status_code}")
            print(f"   响应: {json.dumps(response.json(), ensure_ascii=False, indent=2)}")
        except Exception as e:
            print(f"   错误: {e}")
        print()

    # 测试 6: CORS 预检请求
    print("6. 测试 CORS 预检请求 (OPTIONS /api/v1/labs)")
    try:
        response = requests.options(
            f"{BASE_URL}/api/v1/labs",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Session-Token"
            }
        )
        print(f"   状态码: {response.status_code}")
        print(f"   CORS 头:")
        for header in ["Access-Control-Allow-Origin", "Access-Control-Allow-Methods", "Access-Control-Allow-Headers"]:
            if header in response.headers:
                print(f"     {header}: {response.headers[header]}")
    except Exception as e:
        print(f"   错误: {e}")
    print()

    print("=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    print()
    print("请确保服务器正在运行：python api_server_example.py")
    print()
    input("按 Enter 键开始测试...")
    print()
    test_api_endpoints()
