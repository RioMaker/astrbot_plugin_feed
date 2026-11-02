"""只接受 AstrBot Dashboard 身份的插件页面 API。"""

from __future__ import annotations

import base64
import json
from functools import wraps

from .config import PLUGIN_NAME, FeedError
from .render import MAX_IMAGE_BYTES


class AdminAPI:
    def __init__(self, context, service, web, logger):
        self.context, self.service, self.web, self.logger = (
            context,
            service,
            web,
            logger,
        )
        self.handlers = []

    def register(self):
        for endpoint, handler, method in (
            ("settings", self.settings, "GET"),
            ("settings/save", self.save, "POST"),
            ("preview", self.preview, "POST"),
            ("qr/upload", self.upload, "POST"),
            ("character/upload", self.upload_character, "POST"),
            ("background/upload", self.upload_background, "POST"),
            ("images/read", self.read_image, "POST"),
            ("images/crop", self.crop_image, "POST"),
        ):
            guarded = self.guard(handler)
            self.context.register_web_api(
                f"/{PLUGIN_NAME}/{endpoint}", guarded, [method], "赞助设置"
            )
            self.handlers.append(guarded)

    def close(self):
        self.service.closed = True
        routes = getattr(self.context, "registered_web_apis", None)
        if isinstance(routes, list):
            routes[:] = [item for item in routes if item[1] not in self.handlers]

    def guard(self, handler):
        @wraps(handler)
        async def guarded(*args, **kwargs):
            if self.service.closed:
                return self.web.error_response(
                    "插件已重载，请刷新页面。", status_code=503
                )
            if not self.web.request.username:
                return self.web.error_response(
                    "请先登录 AstrBot 管理面板。", status_code=401
                )
            if (
                self.web.request.headers.get("Sec-Fetch-Site", "").lower()
                == "cross-site"
            ):
                return self.web.error_response(
                    "请通过 AstrBot 管理面板访问。", status_code=403
                )
            try:
                return await handler(*args, **kwargs)
            except FeedError as exc:
                return self.web.error_response(str(exc), status_code=exc.status)
            except Exception as exc:
                self.logger.error(
                    "[feed] 管理页面操作失败: %s (%s)",
                    handler.__name__,
                    type(exc).__name__,
                )
                return self.web.error_response(
                    "操作失败，请检查服务状态后重试。", status_code=500
                )

        return guarded

    def response(self, value):
        return self.web.json_response(value, headers={"Cache-Control": "no-store"})

    async def payload(self):
        if (self.web.request.content_type or "").split(";", 1)[0] != "application/json":
            raise FeedError("请求格式应为 JSON。", 415)
        raw = await self.web.request.body()
        if len(raw) > 16 * 1024:
            raise FeedError("请求过大。", 413)
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise FeedError("无效的 JSON 请求。") from exc
        if not isinstance(value, dict):
            raise FeedError("请求必须是一个对象。")
        return value

    async def settings(self):
        return self.response(self.service.state())

    async def save(self):
        payload = await self.payload()
        return self.response(
            await self.service.save(payload.get("settings"), payload.get("revision"))
        )

    async def preview(self):
        payload = await self.payload()
        content = await self.service.preview(payload.get("settings"))
        return self.response(
            {
                "image": "data:image/png;base64,"
                + base64.b64encode(content).decode("ascii")
            }
        )

    async def upload(self, kind="qr"):
        files = await self.web.request.files()
        upload = files.get("file")
        if not isinstance(upload, self.web.PluginUploadFile):
            raise FeedError("请选择图片。")
        raw = await upload.read(MAX_IMAGE_BYTES + 1)
        path = await self.service.upload(raw, kind)
        return self.response({"path": path})

    async def upload_character(self):
        return await self.upload("character")

    async def upload_background(self):
        return await self.upload("background")

    async def read_image(self):
        data = await self.payload()
        return self.response(
            await self.service.image_info(data.get("kind"), data.get("path"))
        )

    async def crop_image(self):
        data = await self.payload()
        path = await self.service.crop(
            data.get("kind"), data.get("path"), data.get("box")
        )
        return self.response({"path": path})
