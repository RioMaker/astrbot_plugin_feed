from __future__ import annotations

import base64
import importlib.util
import sys
from types import ModuleType, SimpleNamespace

import pytest
from astrbot_plugin_feed.render import ASSETS


@pytest.fixture
def plugin_class(monkeypatch, tmp_path):
    modules = {}
    for name in [
        "astrbot",
        "astrbot.api",
        "astrbot.api.event",
        "astrbot.api.star",
        "astrbot.api.message_components",
    ]:
        modules[name] = ModuleType(name)
        monkeypatch.setitem(sys.modules, name, modules[name])
    modules["astrbot.api"].AstrBotConfig = dict
    modules["astrbot.api"].logger = SimpleNamespace(
        error=lambda *args: None, warning=lambda *args: None
    )
    modules["astrbot.api.event"].AstrMessageEvent = object
    modules["astrbot.api.event"].filter = SimpleNamespace(
        command=lambda name: lambda method: method
    )

    class Star:
        def __init__(self, context):
            self.context = context

    modules["astrbot.api.star"].Star = Star
    modules["astrbot.api.star"].Context = object
    modules["astrbot.api.star"].StarTools = SimpleNamespace(
        get_data_dir=lambda name: tmp_path
    )
    modules["astrbot.api.message_components"].Image = SimpleNamespace(
        fromBase64=lambda value: ("image", base64.b64decode(value))
    )
    spec = importlib.util.spec_from_file_location(
        "astrbot_plugin_feed._test_main", ASSETS.parent / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FeedPlugin


class Event:
    stopped = False

    def stop_event(self):
        self.stopped = True

    def chain_result(self, value):
        return value

    def plain_result(self, value):
        return value


async def test_command_sends_image_without_model(plugin_class, monkeypatch):
    plugin = plugin_class(SimpleNamespace(), {})

    async def image():
        return b"test-image"

    monkeypatch.setattr(plugin.service, "command_image", image)
    event = Event()
    result = [item async for item in plugin.feed(event)]
    assert result == [[("image", b"test-image")]]
    assert event.stopped


async def test_unconfigured_command_and_shutdown(plugin_class):
    plugin = plugin_class(SimpleNamespace(), {})
    event = Event()
    result = [item async for item in plugin.feed(event)]
    assert "二维码" in result[0]
    await plugin.terminate()
    assert plugin.service.closed
