"""图片上传、草稿预览和配置保存共用的服务。"""

from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import io
import os
import uuid
from pathlib import Path

from .config import (
    DEFAULTS,
    FeedError,
    image_field,
    image_path,
    qr_path,
    revision,
    validate_settings,
)
from .render import ASSETS, MAX_IMAGE_BYTES, default_background, load_image, render_card


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
            "template_ready": bool(settings["character_image"])
            or (ASSETS / "keko-feeding.png").is_file(),
        }

    def _read_image(self, path, *, preserve_alpha=False):
        with path.open("rb") as source:
            return load_image(
                source.read(MAX_IMAGE_BYTES + 1), preserve_alpha=preserve_alpha
            )

    def _image(self, settings, kind="qr"):
        field = image_field(kind)
        path = image_path(self.data_dir, field, settings[field])
        if path is None:
            return None
        return self._read_image(path, preserve_alpha=kind != "qr")

    def _render(self, settings):
        return render_card(
            settings,
            self._image(settings),
            character=self._image(settings, "character"),
            background=self._image(settings, "background"),
        )

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

    def _store_image(self, image, kind) -> str:
        folder = image_field(kind)
        upload_dir = self.data_dir / "files" / folder
        upload_dir.mkdir(parents=True, exist_ok=True)
        normalized = io.BytesIO()
        image.save(normalized, format="PNG", optimize=True)
        content = normalized.getvalue()
        if len(content) > MAX_IMAGE_BYTES:
            raise FeedError("转换后的图片超过 8 MB，请缩小图片后重新上传。")
        name = hashlib.sha256(content).hexdigest() + ".png"
        target = upload_dir / name
        if not target.exists():
            temporary = upload_dir / (".upload-" + uuid.uuid4().hex)
            try:
                temporary.write_bytes(content)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return f"files/{folder}/" + name

    def _store_upload(self, raw: bytes, kind: str) -> str:
        image_field(kind)
        return self._store_image(load_image(raw, preserve_alpha=kind != "qr"), kind)

    async def upload(self, raw: bytes, kind: str = "qr") -> str:
        # Windows 不允许两个线程同时替换同一个目标文件。
        async with self.upload_lock, self.image_slots:
            if self.closed:
                raise FeedError("插件已重载，请刷新页面。", 503)
            return await asyncio.to_thread(self._store_upload, raw, kind)

    def _source_image(self, kind, path):
        field = image_field(kind)
        if not isinstance(path, str):
            raise FeedError("请选择图片文件。")
        if not path and kind == "background":
            return default_background()
        if not path and kind == "character":
            target = ASSETS / "keko-feeding.png"
        else:
            target = image_path(self.data_dir, field, [path])
        return self._read_image(target, preserve_alpha=kind != "qr")

    def _image_info(self, kind, path):
        image = self._source_image(kind, path)
        width, height = image.size
        image.thumbnail((1400, 1400))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return {
            "path": path,
            "width": width,
            "height": height,
            "image": "data:image/png;base64,"
            + base64.b64encode(buffer.getvalue()).decode("ascii"),
        }

    async def image_info(self, kind, path):
        async with self.image_slots:
            return await asyncio.to_thread(self._image_info, kind, path)

    def _crop_image(self, kind, path, box):
        image = self._source_image(kind, path)
        if not isinstance(box, dict) or set(box) != {"x", "y", "width", "height"}:
            raise FeedError("裁切区域无效。")
        if any(type(value) is not int for value in box.values()):
            raise FeedError("裁切坐标必须为整数像素。")
        x, y, width, height = (box[key] for key in ("x", "y", "width", "height"))
        if (
            x < 0
            or y < 0
            or width < 80
            or height < 80
            or x + width > image.width
            or y + height > image.height
        ):
            raise FeedError("裁切区域必须位于原图内，且不小于 80 × 80 像素。")
        return self._store_image(image.crop((x, y, x + width, y + height)), kind)

    async def crop(self, kind, path, box):
        async with self.upload_lock, self.image_slots:
            if self.closed:
                raise FeedError("插件已重载，请刷新页面。", 503)
            return await asyncio.to_thread(self._crop_image, kind, path, box)

    async def command_image(self) -> bytes:
        settings = self.settings()
        if not settings["enabled"]:
            raise FeedError("赞助功能暂未开启。")
        if not settings["payment_qr"]:
            raise FeedError(
                "还没有设置付款二维码，请管理员在 AstrBot 的「赞助」插件中上传。"
            )
        if (
            not settings["character_image"]
            and not (ASSETS / "keko-feeding.png").is_file()
        ):
            raise FeedError("赞助图片模板缺失，请管理员重新安装完整插件。")
        async with self.image_slots:

            def generate():
                paths = [
                    qr_path(self.data_dir, settings),
                    image_path(
                        self.data_dir, "character_image", settings["character_image"]
                    ),
                    image_path(
                        self.data_dir, "background_image", settings["background_image"]
                    ),
                ]
                stats = [path.stat() for path in paths if path is not None]
                key = revision(settings) + str(
                    [(stat.st_mtime_ns, stat.st_size) for stat in stats]
                )
                cached = self._cached
                if cached is not None and cached[0] == key:
                    return cached[1]
                content = self._render(settings)
                self._cached = key, content
                return content

            return await asyncio.to_thread(generate)
