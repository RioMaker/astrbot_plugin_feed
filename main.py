from __future__ import annotations

import base64
import importlib

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image
from astrbot.api.star import Context, Star, StarTools

from .admin import AdminAPI
from .config import PLUGIN_NAME, FeedError
from .service import FeedService


class FeedPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.service = FeedService(config, StarTools.get_data_dir(PLUGIN_NAME))
        self.admin = None

    async def initialize(self):
        try:
            web = importlib.import_module("astrbot.api.web")
        except ImportError:
            logger.warning(
                "[feed] 当前版本没有插件视图 API，请使用普通配置上传二维码、修改文案。"
            )
            return
        if callable(getattr(self.context, "register_web_api", None)):
            self.admin = AdminAPI(self.context, self.service, web, logger)
            self.admin.register()

    @filter.command("投喂")
    async def feed(self, event: AstrMessageEvent):
        """查看可可子的赞助二维码。"""
        event.stop_event()
        try:
            image = await self.service.command_image()
            yield event.chain_result(
                [Image.fromBase64(base64.b64encode(image).decode("ascii"))]
            )
        except FeedError as exc:
            yield event.plain_result(str(exc))
        except Exception as exc:
            logger.error("[feed] 生成赞助图片失败 (%s)", type(exc).__name__)
            yield event.plain_result(
                "赞助图片暂时无法生成，请管理员检查二维码与插件资源。"
            )

    async def terminate(self):
        self.service.closed = True
        if self.admin:
            self.admin.close()
