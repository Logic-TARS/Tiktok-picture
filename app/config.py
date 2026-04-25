from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
CONFIG_PATH = DATA_DIR / "config.json"
DOTENV_PATH = ROOT_DIR / ".env"
ENVTXT_PATH = ROOT_DIR / "env.txt"


DEFAULT_CONFIG: dict[str, Any] = {
    "deepseek_api_key": "",
    "deepseek_base_url": "https://api.deepseek.com",
    "deepseek_model": "deepseek-v4-flash",
    "creator_upload_url": "https://creator.douyin.com/creator-micro/content/upload",
    "browser_path": "",
    "browser_profile_dir": str(DATA_DIR / "browser-profile"),
    "publish_mode": "semi_auto",
    "group_size": 4,
    "topic": "二次元图集",
    "account_position": "二次元图片号",
    "caption_style": "治愈收藏向",
    "hashtags_count": 5,
    "publish_interval_seconds": 90,
    "force_9x16_upload": False,
    "force_9x16_mode": "blur_background",
    "upload_selector": "input[type='file']",
    "caption_selector": "",
    "title_selector": "",
}


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "outputs").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "browser-profile").mkdir(parents=True, exist_ok=True)


def load_dotenv() -> None:
    if not DOTENV_PATH.exists():
        return

    content = DOTENV_PATH.read_text(encoding="utf-8").lstrip("\ufeff")
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def load_envtxt() -> None:
    if not ENVTXT_PATH.exists():
        return

    content = ENVTXT_PATH.read_text(encoding="utf-8").lstrip("\ufeff").strip()
    if not content:
        return

    lines = [line.strip() for line in content.splitlines() if line.strip() and not line.strip().startswith("#")]
    if not lines:
        return

    first_line = lines[0]
    if "=" in first_line:
        key, value = first_line.split("=", 1)
        if key.strip() == "DEEPSEEK_API_KEY" and value.strip():
            os.environ.setdefault("DEEPSEEK_API_KEY", value.strip().strip("'\""))
        return

    os.environ.setdefault("DEEPSEEK_API_KEY", first_line)


def load_config() -> dict[str, Any]:
    ensure_data_dirs()
    load_dotenv()
    load_envtxt()
    config = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                config.update(saved)
        except json.JSONDecodeError:
            pass

    env_map = {
        "DEEPSEEK_API_KEY": "deepseek_api_key",
        "DEEPSEEK_BASE_URL": "deepseek_base_url",
        "DEEPSEEK_MODEL": "deepseek_model",
        "DOUYIN_CREATOR_UPLOAD_URL": "creator_upload_url",
        "BROWSER_PATH": "browser_path",
        "BROWSER_PROFILE_DIR": "browser_profile_dir",
        "UPLOAD_SELECTOR": "upload_selector",
        "TITLE_SELECTOR": "title_selector",
        "CAPTION_SELECTOR": "caption_selector",
    }
    for env_name, key in env_map.items():
        value = os.getenv(env_name)
        if value:
            config[key] = value
    config["hashtags_count"] = max(1, min(5, int(config.get("hashtags_count") or DEFAULT_CONFIG["hashtags_count"])))
    return config


def save_config(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_data_dirs()
    current = load_config()
    allowed = set(DEFAULT_CONFIG)
    for key, value in payload.items():
        if key in allowed:
            if key == "group_size":
                value = max(1, int(value or DEFAULT_CONFIG[key]))
            if key == "hashtags_count":
                value = max(1, min(5, int(value or DEFAULT_CONFIG[key])))
            if key == "publish_interval_seconds":
                value = max(0, int(value or DEFAULT_CONFIG[key]))
            if key == "force_9x16_upload":
                value = bool(value)
            if key == "force_9x16_mode":
                if value not in {"blur_background", "crop_center"}:
                    value = DEFAULT_CONFIG[key]
            current[key] = value
    CONFIG_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return current


def public_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    data = (config or load_config()).copy()
    key = data.get("deepseek_api_key") or ""
    data["deepseek_api_key_set"] = bool(key)
    data["deepseek_api_key"] = "********" if key else ""
    return data
