"""WeChat API integration for miniprogram and official account login."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import requests


@dataclass
class WeChatConfig:
    """微信配置"""

    miniprogram_appid: str = ""
    miniprogram_secret: str = ""
    officialaccount_appid: str = ""
    officialaccount_secret: str = ""


@dataclass
class WeChatSession:
    """微信登录会话信息"""

    openid: str
    session_key: str = ""
    unionid: str = ""
    errcode: int = 0
    errmsg: str = ""


class WeChatAPIError(Exception):
    """微信 API 错误"""

    def __init__(self, errcode: int, errmsg: str):
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(f"WeChat API Error {errcode}: {errmsg}")


def miniprogram_code_to_session(appid: str, secret: str, code: str) -> WeChatSession:
    """
    小程序 code 换取 session_key 和 openid/unionid。

    :param appid: 小程序 AppID
    :param secret: 小程序 AppSecret
    :param code: wx.login() 返回的 code
    :return: WeChatSession 对象
    :raises WeChatAPIError: 微信 API 返回错误
    """
    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": appid,
        "secret": secret,
        "js_code": code,
        "grant_type": "authorization_code",
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
    except Exception as e:
        raise WeChatAPIError(-1, f"Network error: {str(e)}")

    if "errcode" in data and data["errcode"] != 0:
        raise WeChatAPIError(data["errcode"], data.get("errmsg", "Unknown error"))

    return WeChatSession(
        openid=data.get("openid", ""),
        session_key=data.get("session_key", ""),
        unionid=data.get("unionid", ""),
    )


def get_official_account_oauth_url(
    appid: str,
    redirect_uri: str,
    scope: str = "snsapi_base",
    state: str = "STATE",
) -> str:
    """
    生成公众号网页授权 URL。

    :param appid: 公众号 AppID
    :param redirect_uri: 授权回调地址（需要 URL 编码）
    :param scope: snsapi_base（静默授权）或 snsapi_userinfo（获取用户信息）
    :param state: 自定义参数，用于防止 CSRF 攻击
    :return: 授权 URL
    """
    redirect_uri_encoded = quote(redirect_uri, safe="")
    return (
        f"https://open.weixin.qq.com/connect/oauth2/authorize"
        f"?appid={appid}"
        f"&redirect_uri={redirect_uri_encoded}"
        f"&response_type=code"
        f"&scope={scope}"
        f"&state={state}#wechat_redirect"
    )


def get_official_account_access_token(appid: str, secret: str, code: str) -> dict:
    """
    通过 code 换取公众号网页授权 access_token 和 openid/unionid。

    :param appid: 公众号 AppID
    :param secret: 公众号 AppSecret
    :param code: 授权回调返回的 code
    :return: 包含 access_token、openid、unionid 的字典
    :raises WeChatAPIError: 微信 API 返回错误
    """
    url = "https://api.weixin.qq.com/sns/oauth2/access_token"
    params = {
        "appid": appid,
        "secret": secret,
        "code": code,
        "grant_type": "authorization_code",
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
    except Exception as e:
        raise WeChatAPIError(-1, f"Network error: {str(e)}")

    if "errcode" in data and data["errcode"] != 0:
        raise WeChatAPIError(data["errcode"], data.get("errmsg", "Unknown error"))

    return data


def generate_wechat_scheme(
    access_token: str,
    page_path: str,
    query: str = "",
    expire_days: int = 30,
) -> str:
    """
    生成微信小程序 URL Scheme。

    :param access_token: 小程序 access_token
    :param page_path: 跳转页面路径
    :param query: 页面参数
    :param expire_days: 有效期（天），最长 30 天
    :return: scheme URL
    :raises WeChatAPIError: 微信 API 返回错误
    """
    url = "https://api.weixin.qq.com/wxa/generatescheme"
    params = {"access_token": access_token}
    data = {
        "jump_wxa": {
            "path": page_path,
            "query": query,
        },
        "expire_type": 0,  # 到期失效
        "expire_interval": expire_days,
    }

    try:
        resp = requests.post(url, params=params, json=data, timeout=10)
        result = resp.json()
    except Exception as e:
        raise WeChatAPIError(-1, f"Network error: {str(e)}")

    if result.get("errcode", 0) != 0:
        raise WeChatAPIError(result["errcode"], result.get("errmsg", "Unknown error"))

    return result.get("openlink", "")


def get_miniprogram_access_token(appid: str, secret: str) -> str:
    """
    获取小程序 access_token（用于调用其他微信 API）。

    :param appid: 小程序 AppID
    :param secret: 小程序 AppSecret
    :return: access_token
    :raises WeChatAPIError: 微信 API 返回错误
    """
    url = "https://api.weixin.qq.com/cgi-bin/token"
    params = {
        "grant_type": "client_credential",
        "appid": appid,
        "secret": secret,
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
    except Exception as e:
        raise WeChatAPIError(-1, f"Network error: {str(e)}")

    if "errcode" in data and data["errcode"] != 0:
        raise WeChatAPIError(data["errcode"], data.get("errmsg", "Unknown error"))

    return data.get("access_token", "")


def set_official_account_menu(access_token: str, menu_config: dict) -> bool:
    """
    设置公众号自定义菜单。

    :param access_token: 公众号 access_token
    :param menu_config: 菜单配置（JSON 格式）
    :return: 是否成功
    :raises WeChatAPIError: 微信 API 返回错误
    """
    url = "https://api.weixin.qq.com/cgi-bin/menu/create"
    params = {"access_token": access_token}

    try:
        resp = requests.post(url, params=params, json=menu_config, timeout=10)
        result = resp.json()
    except Exception as e:
        raise WeChatAPIError(-1, f"Network error: {str(e)}")

    if result.get("errcode", 0) != 0:
        raise WeChatAPIError(result["errcode"], result.get("errmsg", "Unknown error"))

    return True
