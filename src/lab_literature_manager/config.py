"""Configuration loader for WeChat integration."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    """应用配置"""

    # 微信小程序
    wechat_miniprogram_appid: str
    wechat_miniprogram_secret: str

    # 微信公众号
    wechat_officialaccount_appid: str
    wechat_officialaccount_secret: str

    # 数据目录
    data_dir: str

    # 服务器配置
    server_host: str
    server_port: int


def load_config(env_file: str = ".env") -> Config:
    """
    从环境变量或 .env 文件加载配置。

    :param env_file: .env 文件路径
    :return: Config 对象
    """
    # 尝试加载 .env 文件
    env_path = Path(env_file)
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    # 只在环境变量不存在时设置
                    if key not in os.environ:
                        os.environ[key] = value

    return Config(
        wechat_miniprogram_appid=os.getenv("WECHAT_MINIPROGRAM_APPID", ""),
        wechat_miniprogram_secret=os.getenv("WECHAT_MINIPROGRAM_SECRET", ""),
        wechat_officialaccount_appid=os.getenv("WECHAT_OFFICIALACCOUNT_APPID", ""),
        wechat_officialaccount_secret=os.getenv("WECHAT_OFFICIALACCOUNT_SECRET", ""),
        data_dir=os.getenv("DATA_DIR", "data/local"),
        server_host=os.getenv("SERVER_HOST", "0.0.0.0"),
        server_port=int(os.getenv("SERVER_PORT", "8080")),
    )
