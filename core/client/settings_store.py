# coding: utf-8
"""
用户设置持久化

极简的 JSON 设置文件，用于保存运行时用户偏好（如选中的全局快捷键）。
存放在项目根目录的 settings.json。损坏时回退默认值。
"""
import json
import os
from pathlib import Path

# 设置文件路径：项目根目录 / settings.json
# config_client.py 的 BASE_DIR 即项目根
from config_client import BASE_DIR

_SETTINGS_PATH = Path(BASE_DIR) / 'settings.json'


def load_settings() -> dict:
    """读取全部设置。文件不存在或损坏时返回空 dict。"""
    try:
        if _SETTINGS_PATH.exists():
            with open(_SETTINGS_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return {}


def save_settings(data: dict) -> None:
    """覆写保存全部设置。失败时静默（不影响主流程）。"""
    try:
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_SETTINGS_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_setting(key: str, default=None):
    """读取单个设置项。"""
    return load_settings().get(key, default)


def set_setting(key: str, value) -> None:
    """写入单个设置项（读-改-写）。"""
    data = load_settings()
    data[key] = value
    save_settings(data)
