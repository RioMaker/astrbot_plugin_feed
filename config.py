"""配置校验与文件边界；不依赖 AstrBot，便于离线验证。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

PLUGIN_NAME = "astrbot_plugin_feed"
DEFAULTS = {
    "enabled": True,
    "payment_qr": [],
    "bubble_text": "谢谢你的投喂！\n可可子会继续努力哒～",
    "footer_text": "自愿赞助 · 感谢每一份心意",
}


class FeedError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def validate_settings(value: dict) -> dict:
    if not isinstance(value, dict):
        raise FeedError("设置必须是一个对象。")
    unknown = set(value) - set(DEFAULTS)
    if unknown:
        raise FeedError("设置中包含不支持的字段。")
    settings = {**DEFAULTS, **value}
    if not isinstance(settings["enabled"], bool):
        raise FeedError("启用状态必须为布尔值。")
    paths = settings["payment_qr"]
    if not isinstance(paths, list) or len(paths) > 1:
        raise FeedError("付款二维码请只保留一张图片。")
    for path in paths:
        if not isinstance(path, str) or len(path) > 240:
            raise FeedError("二维码文件路径无效。")
        parts = PurePosixPath(path).parts
        if (
            not path.startswith("files/payment_qr/")
            or len(parts) < 3
            or ".." in parts
            or "\\" in path
            or ":" in path
            or "\x00" in path
            or PurePosixPath(path).suffix.lower()
            not in {".png", ".jpg", ".jpeg", ".webp"}
        ):
            raise FeedError("请选择在本插件中上传的二维码图片。")
    settings["payment_qr"] = list(paths)
    for name, limit in (("bubble_text", 120), ("footer_text", 32)):
        text = settings[name]
        if not isinstance(text, str):
            raise FeedError("文案必须为文字。")
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if len(text) > limit:
            label = "气泡文案" if name == "bubble_text" else "下方说明"
            raise FeedError(f"{label}最多 {limit} 字。")
        if re.search(r"[\x00-\x09\x0b-\x1f\x7f]", text):
            raise FeedError("文案含有不支持的控制字符。")
        if text.count("\n") > (3 if name == "bubble_text" else 0):
            raise FeedError("气泡文案最多 4 个段落，下方说明请保持一行。")
        settings[name] = text
    if not settings["bubble_text"]:
        raise FeedError("请填写气泡文案。")
    return settings


def revision(settings: dict) -> str:
    return hashlib.sha256(
        json.dumps(settings, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def qr_path(data_dir: Path, settings: dict) -> Path | None:
    if not settings["payment_qr"]:
        return None
    root = (data_dir / "files" / "payment_qr").resolve()
    path = (data_dir / settings["payment_qr"][0]).resolve()
    if not path.is_relative_to(root) or path == root:
        raise FeedError("二维码文件超出本插件的存储目录。")
    if not path.is_file():
        raise FeedError("二维码图片不存在，请重新上传。")
    return path
