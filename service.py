"""图片上传、草稿预览和配置保存共用的服务。"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import io
import os
import uuid
from pathlib import Path

from .config import DEFAULTS, FeedError, qr_path, revision, validate_settings
from .render import ASSETS, MAX_IMAGE_BYTES, load_image, render_card


class FeedService:
    def __init__(self, config, data_dir: Path):
        self.config = config
        self.data_dir = Path(data_dir).resolve()
        self.upload_dir = self.data_dir / "files" / "payment_qr"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.lock = asyncio.Lock()
        self.upload_lock = asyncio.Lock()
        self.image_slots = asyncio.Semaphore(2)
        self.closed = False
        self._cached: tuple[str, bytes] | None = None

    def settings(self) -> dict:
        return validate_settings(
            {key: self.config.get(key, value) for key, value in DEFAULTS.items()}
        )

    def state(self) -> dict:
        settings = self.settings()
        return {
            "settings": settings,
            "revision": revision(settings),
            "template_ready": (ASSETS / "keko-feeding.png").is_file(),
        }

    def _image(self, settings):
        path = qr_path(self.data_dir, settings)
        if path is None:
            return None
        with path.open("rb") as source:
            return load_image(source.read(MAX_IMAGE_BYTES + 1))

    def _render(self, settings):
        return render_card(settings, self._image(settings))

    async def preview(self, settings: dict) -> bytes:
        settings = validate_settings(settings)
        async with self.image_slots:
            return await asyncio.to_thread(self._render, settings)

    async def save(self, settings: dict, expected_revision: str) -> dict:
        settings = validate_settings(settings)
        # Validate the actual image and text fit before mutating any configuration.
        await self.preview(settings)
        async with self.lock:
            if self.closed:
                raise FeedError("插件已重载，请刷新页面。", 503)
            if expected_revision != revision(self.settings()):
                raise FeedError("配置已在其他页面修改，请重新载入后再保存。", 409)
            previous = copy.deepcopy(dict(self.config))
            try:
                self.config.update(settings)
                self.config.save_config()
            except Exception:
                self.config.clear()
                self.config.update(previous)
                raise
            self._cached = None
            return self.state()

    def _store_upload(self, raw: bytes) -> str:
        image = load_image(raw)
        normalized = io.BytesIO()
        image.save(normalized, format="PNG", optimize=True)
        content = normalized.getvalue()
        if len(content) > MAX_IMAGE_BYTES:
            raise FeedError("转换后的图片超过 8 MB，请缩小图片后重新上传。")
        name = hashlib.sha256(content).hexdigest() + ".png"
        target = self.upload_dir / name
        if not target.exists():
            temporary = self.upload_dir / (".upload-" + uuid.uuid4().hex)
            try:
                temporary.write_bytes(content)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return "files/payment_qr/" + name

    async def upload(self, raw: bytes) -> str:
        # Windows 不允许两个线程同时替换同一个目标文件。
        async with self.upload_lock, self.image_slots:
            if self.closed:
                raise FeedError("插件已重载，请刷新页面。", 503)
            return await asyncio.to_thread(self._store_upload, raw)

    async def command_image(self) -> bytes:
        settings = self.settings()
        if not settings["enabled"]:
            raise FeedError("赞助功能暂未开启。")
        if not settings["payment_qr"]:
            raise FeedError(
                "还没有设置付款二维码，请管理员在 AstrBot 的「赞助」插件中上传。"
            )
        if not (ASSETS / "keko-feeding.png").is_file():
            raise FeedError("赞助图片模板缺失，请管理员重新安装完整插件。")
        async with self.image_slots:

            def generate():
                path = qr_path(self.data_dir, settings)
                stat = path.stat()
                key = revision(settings) + f":{stat.st_mtime_ns}:{stat.st_size}"
                cached = self._cached
                if cached is not None and cached[0] == key:
                    return cached[1]
                content = self._render(settings)
                self._cached = key, content
                return content

            return await asyncio.to_thread(generate)
