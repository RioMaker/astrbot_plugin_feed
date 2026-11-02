from __future__ import annotations

import asyncio
import base64
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import qrcode
import zxingcpp
from astrbot_plugin_feed.admin import AdminAPI
from astrbot_plugin_feed.config import DEFAULTS, FeedError, qr_path, validate_settings
from astrbot_plugin_feed.render import ASSETS, QR_BOX, load_image, render_card
from astrbot_plugin_feed.service import FeedService
from PIL import Image, ImageChops


class Config(dict):
    def __init__(self):
        super().__init__(copy.deepcopy(DEFAULTS))
        self.saved = 0
        self.fail = False

    def save_config(self):
        if self.fail:
            raise OSError("cannot save")
        self.saved += 1


def image_bytes(image):
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def code():
    value = "https://example.invalid/feed-test/ONLY-A-TEST"
    image = qrcode.make(value, box_size=12, border=4).convert("RGB")
    return value, image, image_bytes(image)


@pytest.fixture
def service(tmp_path):
    return FeedService(Config(), tmp_path)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"enabled": 1},
        {"unknown": 1},
        {"bubble_text": ""},
        {"bubble_text": "字" * 121},
        {"bubble_text": "a\nb\nc\nd\ne"},
        {"footer_text": "a\nb"},
        {"footer_text": "字" * 33},
        {"payment_qr": "a"},
        {"payment_qr": ["a", "b"]},
        {"payment_qr": ["../secret.png"]},
        {"payment_qr": ["files/payment_qr/../../secret.png"]},
        {"payment_qr": ["C:\\private.png"]},
        {"payment_qr": ["files/payment_qr/x.svg"]},
        {"bubble_text": "a\x00b"},
    ],
)
def test_invalid_settings(payload):
    with pytest.raises(FeedError):
        validate_settings(payload)


def test_defaults_match_schema():
    schema = json.loads(
        (ASSETS.parent / "_conf_schema.json").read_text(encoding="utf-8")
    )
    assert {key: entry["default"] for key, entry in schema.items()} == DEFAULTS


def test_image_input_rejects_invalid_small_and_oversize():
    for data in (
        b"not an image",
        b"x" * (8 * 1024 * 1024 + 1),
        image_bytes(Image.new("RGB", (10, 10))),
        image_bytes(Image.new("RGB", (6001, 80))),
    ):
        with pytest.raises(FeedError):
            load_image(data)


def test_alpha_becomes_white():
    image = load_image(image_bytes(Image.new("RGBA", (100, 100), (0, 0, 0, 0))))
    assert image.getpixel((50, 50)) == (255, 255, 255)


@pytest.mark.parametrize(
    "text",
    [
        DEFAULTS["bubble_text"],
        "感谢" * 60,
        "谢谢你！\n今天也要开心\n每一份支持\n可可子都记得",
    ],
)
def test_real_qr_survives_composition(code, text):
    value, qr, _ = code
    content = render_card({**DEFAULTS, "bubble_text": text}, qr)
    result = Image.open(io.BytesIO(content))
    assert result.size == (1080, 1440)
    assert zxingcpp.read_barcode(result).text == value
    # 模拟聊天端缩图，二维码仍应可解码。
    assert zxingcpp.read_barcode(result.resize((540, 720))).text == value


def test_character_does_not_cover_qr(code, tmp_path):
    _, qr, _ = code
    normal = Image.open(io.BytesIO(render_card(DEFAULTS, qr)))
    # 一张完全不透明的角色占位也不能覆盖码区。
    replacement = tmp_path / "solid.png"
    Image.new("RGBA", (800, 800), "red").save(replacement)
    other = Image.open(io.BytesIO(render_card(DEFAULTS, qr, replacement)))
    assert (
        ImageChops.difference(normal.crop(QR_BOX), other.crop(QR_BOX)).getbbox() is None
    )


def test_rectangle_is_not_cropped(code):
    value, qr, _ = code
    large = Image.new("RGB", (qr.width + 120, qr.height + 260), "white")
    large.paste(qr, (60, 100))
    result = Image.open(io.BytesIO(render_card(DEFAULTS, large)))
    assert zxingcpp.read_barcode(result).text == value


async def test_upload_preview_save_and_reload(service, code):
    initial = service.state()
    path = await service.upload(code[2])
    assert service.settings()["payment_qr"] == []
    draft = {**initial["settings"], "payment_qr": [path], "bubble_text": "谢谢投喂！"}
    preview = await service.preview(draft)
    assert service.config.saved == 0
    state = await service.save(draft, initial["revision"])
    assert state["revision"] != initial["revision"]
    assert await service.command_image() == preview
    reloaded = FeedService(service.config, service.data_dir)
    assert await reloaded.command_image() == preview
    assert service.config.saved == 1


async def test_stale_save_cannot_overwrite(service):
    state = service.state()
    await service.save(
        {**state["settings"], "bubble_text": "第一次"}, state["revision"]
    )
    with pytest.raises(FeedError) as error:
        await service.save(
            {**state["settings"], "bubble_text": "第二次"}, state["revision"]
        )
    assert error.value.status == 409
    assert service.settings()["bubble_text"] == "第一次"


async def test_failed_save_restores_memory(service):
    state = service.state()
    service.config.fail = True
    with pytest.raises(OSError):
        await service.save(
            {**state["settings"], "bubble_text": "不应生效"}, state["revision"]
        )
    assert service.state() == state


async def test_missing_and_disabled_command(service):
    with pytest.raises(FeedError, match="二维码"):
        await service.command_image()
    service.config["enabled"] = False
    with pytest.raises(FeedError, match="未开启"):
        await service.command_image()


async def test_deduplicated_upload_and_concurrent_commands(service, code):
    one, two = await asyncio.gather(service.upload(code[2]), service.upload(code[2]))
    assert one == two
    service.config["payment_qr"] = [one]
    results = await asyncio.gather(*(service.command_image() for _ in range(5)))
    assert len(set(results)) == 1
    assert len(list(service.upload_dir.glob("*.png"))) == 1


async def test_native_config_file_and_edit_are_used(service, code):
    path = service.upload_dir / "native.png"
    path.write_bytes(code[2])
    service.config["payment_qr"] = ["files/payment_qr/native.png"]
    first = await service.command_image()
    service.config["bubble_text"] = "原生配置更新"
    assert await service.command_image() != first
    path.unlink()
    with pytest.raises(FeedError):
        await service.command_image()


def test_path_escape_symlink(service, tmp_path):
    outer = tmp_path / "secret.png"
    outer.write_bytes(b"x")
    link = service.upload_dir / "escape.png"
    try:
        link.symlink_to(outer)
    except OSError:
        pytest.skip("Windows 当前用户未启用符号链接权限")
    with pytest.raises(FeedError):
        qr_path(
            service.data_dir,
            {**DEFAULTS, "payment_qr": ["files/payment_qr/escape.png"]},
        )


class Request:
    username = "admin"
    headers = {}
    content_type = "application/json"
    data = {}

    async def body(self):
        return json.dumps(self.data).encode()


def api_fixture(service):
    request = Request()
    routes = []
    web = SimpleNamespace(
        request=request,
        json_response=lambda value, **kw: (value, 200),
        error_response=lambda value, status_code=400: (value, status_code),
    )
    context = SimpleNamespace(
        registered_web_apis=routes, register_web_api=lambda *args: routes.append(args)
    )
    api = AdminAPI(context, service, web, SimpleNamespace(error=lambda *args: None))
    api.register()
    return api, request, routes


async def test_all_admin_routes_require_dashboard_identity(service):
    api, request, routes = api_fixture(service)
    request.username = None
    for route in routes:
        assert (await route[1]())[1] == 401
    request.username = "admin"
    request.headers = {"Sec-Fetch-Site": "cross-site"}
    assert (await routes[0][1]())[1] == 403
    api.close()
    assert routes == []


async def test_admin_preview_does_not_save_and_errors(service):
    api, request, routes = api_fixture(service)
    request.data = {"settings": DEFAULTS}
    value, status = await routes[2][1]()
    assert status == 200
    assert base64.b64decode(value["image"].split(",")[1]).startswith(b"\x89PNG")
    assert service.config.saved == 0
    request.data = []
    assert (await routes[2][1]())[1] == 400
    request.content_type = "text/plain"
    assert (await routes[2][1]())[1] == 415


def test_page_entries_are_synchronized():
    root = Path(__file__).resolve().parents[1]
    for filename in ("index.html", "app.js", "style.css", "cropper.js"):
        assert (root / "pages/settings" / filename).read_bytes() == (
            root / "views/settings" / filename
        ).read_bytes()


async def test_crop_payment_screenshot_keeps_code_and_source(service, code):
    value, qr, raw = code
    screenshot = Image.new("RGB", (qr.width + 160, qr.height + 300), "#aaddaa")
    screenshot.paste(qr, (80, 140))
    source = await service.upload(image_bytes(screenshot))
    original = (service.data_dir / source).read_bytes()
    target = await service.crop(
        "qr", source, {"x": 80, "y": 140, "width": qr.width, "height": qr.height}
    )
    assert target != source
    assert (service.data_dir / source).read_bytes() == original
    assert service.settings()["payment_qr"] == []
    draft = {**service.settings(), "payment_qr": [target]}
    result = Image.open(io.BytesIO(await service.preview(draft)))
    assert zxingcpp.read_barcode(result).text == value


async def test_custom_template_crop_and_restore_default(service, code):
    service.config["payment_qr"] = [await service.upload(code[2])]
    before = await service.command_image()
    default_asset = (ASSETS / "keko-feeding.png").read_bytes()
    custom = Image.new("RGBA", (500, 240), (0, 0, 0, 0))
    custom.paste((245, 25, 25, 255), (80, 80, 420, 200))
    source = await service.upload(image_bytes(custom), "character")
    cropped = await service.crop(
        "character", source, {"x": 40, "y": 40, "width": 420, "height": 180}
    )
    with Image.open(service.data_dir / cropped) as image:
        assert image.size == (420, 180)
        assert image.getchannel("A").getextrema() == (0, 255)
    state = service.state()
    await service.save(
        {**state["settings"], "character_image": [cropped]}, state["revision"]
    )
    after = await service.command_image()
    assert before != after
    assert (
        ImageChops.difference(
            Image.open(io.BytesIO(before)).crop(QR_BOX),
            Image.open(io.BytesIO(after)).crop(QR_BOX),
        ).getbbox()
        is None
    )
    state = service.state()
    await service.save({**state["settings"], "character_image": []}, state["revision"])
    assert await service.command_image() == before
    assert (ASSETS / "keko-feeding.png").read_bytes() == default_asset
    assert (service.data_dir / source).exists()


@pytest.mark.parametrize(
    "box",
    [
        None,
        {},
        {"x": -1, "y": 0, "width": 80, "height": 80},
        {"x": 1.5, "y": 0, "width": 80, "height": 80},
        {"x": True, "y": 0, "width": 80, "height": 80},
        {"x": 0, "y": 0, "width": 79, "height": 80},
        {"x": 0, "y": 0, "width": 9999, "height": 80},
    ],
)
async def test_invalid_crops_leave_upload_unchanged(service, code, box):
    path = await service.upload(code[2])
    before = (service.data_dir / path).read_bytes()
    with pytest.raises(FeedError):
        await service.crop("qr", path, box)
    assert (service.data_dir / path).read_bytes() == before
    assert len(list(service.upload_dir.glob("*.png"))) == 1


async def test_asset_reader_rejects_other_kind_and_path(service, code):
    path = await service.upload(code[2])
    for kind, source in [
        ("unsupported", path),
        ("character", path),
        ("background", path),
        ("qr", "../private.png"),
        ("qr", "files/payment_qr/../../private.png"),
    ]:
        with pytest.raises(FeedError):
            await service.image_info(kind, source)


async def test_title_migration_save_and_render(service, code):
    service.config.pop("card_title")
    service.config.pop("character_image")
    assert service.settings()["card_title"] == "赞助"
    assert service.settings()["character_image"] == []
    service.config["payment_qr"] = [await service.upload(code[2])]
    before = Image.open(io.BytesIO(await service.command_image()))
    state = service.state()
    await service.save(
        {**state["settings"], "card_title": "可可子投喂站"}, state["revision"]
    )
    after = Image.open(io.BytesIO(await service.command_image()))
    bounds = ImageChops.difference(before, after).getbbox()
    assert bounds and bounds[1] >= 70 and bounds[3] <= 147
    assert zxingcpp.read_barcode(after).text == code[0]


@pytest.mark.parametrize("title", ["", "\n", "字" * 21, "第一行\n第二行"])
def test_invalid_titles(title):
    with pytest.raises(FeedError):
        validate_settings({"card_title": title})


async def test_background_and_character_restore_independently(service, code):
    service.config.pop("background_image")  # 0.2.0 配置无需迁移文件即可使用。
    service.config["payment_qr"] = [await service.upload(code[2])]
    service.config["card_title"] = "可可子投喂站"
    before = await service.command_image()
    assert service.settings()["background_image"] == []
    character = await service.upload(
        image_bytes(Image.new("RGBA", (800, 336), (220, 50, 80, 128))), "character"
    )
    background = await service.upload(
        image_bytes(Image.new("RGB", (1080, 1440), "#eadfff")), "background"
    )
    state = service.state()
    both = {
        **state["settings"],
        "character_image": [character],
        "background_image": [background],
    }
    preview = await service.preview(both)
    assert await service.command_image() == before  # 上传、预览不会提前生效。
    await service.save(both, state["revision"])
    result = await service.command_image()
    assert result == preview
    assert zxingcpp.read_barcode(Image.open(io.BytesIO(result))).text == code[0]

    state = service.state()
    await service.save({**state["settings"], "character_image": []}, state["revision"])
    assert service.settings()["background_image"] == [background]
    assert Image.open(io.BytesIO(await service.command_image())).getpixel((0, 0)) == (
        234,
        223,
        255,
    )

    state = service.state()
    await service.save(
        {**state["settings"], "character_image": [character], "background_image": []},
        state["revision"],
    )
    assert service.settings()["character_image"] == [character]
    assert service.settings()["card_title"] == "可可子投喂站"
    assert service.settings()["payment_qr"] == both["payment_qr"]
    assert await service.command_image() == await service.preview(
        {**both, "background_image": []}
    )

    state = service.state()
    await service.save({**state["settings"], "character_image": []}, state["revision"])
    assert await service.command_image() == before
    assert (service.data_dir / character).exists()
    assert (service.data_dir / background).exists()


async def test_background_default_preview_crop_and_alpha(service):
    info = await service.image_info("background", "")
    assert (info["width"], info["height"]) == (1080, 1440)
    source = Image.new("RGBA", (400, 600), (0, 0, 0, 0))
    source.paste((40, 70, 200, 255), (100, 100, 300, 500))
    path = await service.upload(image_bytes(source), "background")
    cropped = await service.crop(
        "background", path, {"x": 50, "y": 100, "width": 300, "height": 400}
    )
    with Image.open(service.data_dir / cropped) as image:
        assert image.size == (300, 400)
        assert image.getchannel("A").getextrema() == (0, 255)
    assert service.settings()["background_image"] == []
    assert (service.data_dir / path).exists()
    # 默认底图也可裁切，产生独立文件，默认图始终可以重新恢复。
    await service.crop("background", "", {"x": 0, "y": 0, "width": 540, "height": 720})
    assert await service.image_info("background", "") == info


def test_background_preserves_qr_and_contains_whole_image(code):
    square = Image.new("RGB", (400, 400), "#eadfff")
    result = Image.open(io.BytesIO(render_card(DEFAULTS, code[1], background=square)))
    assert result.getpixel((0, 0)) == (249, 247, 237)  # 非 3:4 图片等比居中留白。
    assert result.getpixel((0, 720)) == (234, 223, 255)
    transparent = Image.new("RGBA", (108, 144), (50, 60, 70, 0))
    other = Image.open(
        io.BytesIO(render_card(DEFAULTS, code[1], background=transparent))
    )
    assert other.getpixel((0, 720)) == (249, 247, 237)
    baseline = Image.open(io.BytesIO(render_card(DEFAULTS, code[1])))
    assert (
        ImageChops.difference(baseline.crop(QR_BOX), result.crop(QR_BOX)).getbbox()
        is None
    )
    assert zxingcpp.read_barcode(result.resize((540, 720))).text == code[0]


async def test_native_background_update_invalidates_command_cache(service, code):
    service.config["payment_qr"] = [await service.upload(code[2])]
    path = service.data_dir / "files/background_image/native.png"
    path.parent.mkdir(parents=True)
    Image.new("RGB", (108, 144), "#eadfff").save(path)
    service.config["background_image"] = ["files/background_image/native.png"]
    first = await service.command_image()
    Image.new("RGB", (216, 288), "#ffeadd").save(path)
    second = await service.command_image()
    assert first != second
    assert Image.open(io.BytesIO(second)).getpixel((0, 0)) == (255, 234, 221)
    assert await FeedService(service.config, service.data_dir).command_image() == second
