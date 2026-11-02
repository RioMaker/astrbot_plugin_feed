"""将生成的角色、可编辑气泡和原始收款码合成为 PNG。"""

from __future__ import annotations

import io
import warnings
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from .config import FeedError

ASSETS = Path(__file__).resolve().parent / "assets"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 16_000_000
CARD_SIZE = (1080, 1440)
QR_BOX = (280, 752, 800, 1272)
CHARACTER_BOX = (140, 400, 940, 736)


def load_image(data: bytes, *, preserve_alpha: bool = False) -> Image.Image:
    """限制解码成本；角色保留透明度，二维码的透明背景合并为白色。"""
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise FeedError("图片不能为空，且不能超过 8 MB。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise FeedError("仅支持 PNG、JPG 和 WebP 图片。")
                if source.width * source.height > MAX_PIXELS or max(source.size) > 6000:
                    raise FeedError(
                        "图片过大，请使用不超过 1600 万像素、边长 6000 的图片。"
                    )
                if min(source.size) < 80:
                    raise FeedError("图片太小，请上传至少 80 × 80 像素的图片。")
                if getattr(source, "n_frames", 1) != 1:
                    raise FeedError("请上传静态图片。")
                rgba = ImageOps.exif_transpose(source).convert("RGBA")
                if preserve_alpha:
                    return rgba
                white = Image.new("RGBA", rgba.size, "white")
                white.alpha_composite(rgba)
                return white.convert("RGB")
    except FeedError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise FeedError("无法读取图片，请重新上传有效的 PNG、JPG 或 WebP。") from exc


@lru_cache(maxsize=32)
def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ASSETS / "fonts" / "FeedSans.otf"), size)


def wrap_text(
    text: str, selected_font: ImageFont.FreeTypeFont, width: int
) -> list[str]:
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for char in paragraph:
            if line and selected_font.getlength(line + char) > width:
                lines.append(line)
                line = char
            else:
                line += char
        lines.append(line)
    return lines


def fit_text(text: str, width: int, height: int, maximum: int = 46):
    for size in range(maximum, 21, -1):
        selected = font(size)
        lines = wrap_text(text, selected, width)
        if len(lines) * (size + 12) <= height:
            return selected, lines, size + 12
    raise FeedError("文案在气泡中放不下，请减少文字或换行。")


def _center(draw: ImageDraw.ImageDraw, text: str, y: int, size: int, fill: str):
    draw.text((540, y), text, font=font(size), fill=fill, anchor="mt")


def default_background() -> Image.Image:
    """可单独预览、裁切或恢复的默认底图，不含文字和其他图层。"""
    canvas = Image.new("RGB", CARD_SIZE, "#f9f7ed")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((32, 32, 1048, 1408), radius=60, fill="#edf3da")
    draw.ellipse((-160, 1020, 270, 1450), fill="#e1ebc6")
    draw.ellipse((870, -130, 1230, 230), fill="#e1ebc6")
    return canvas


def render_card(
    settings: dict,
    qr: Image.Image | None,
    character_path: Path | None = None,
    *,
    character: Image.Image | None = None,
    background: Image.Image | None = None,
) -> bytes:
    if background is None:
        canvas = default_background()
    else:
        canvas = Image.new("RGB", CARD_SIZE, "#f9f7ed")
        contained = ImageOps.contain(
            background.convert("RGBA"), CARD_SIZE, Image.Resampling.LANCZOS
        )
        canvas.paste(
            contained,
            (
                (CARD_SIZE[0] - contained.width) // 2,
                (CARD_SIZE[1] - contained.height) // 2,
            ),
            contained,
        )
    draw = ImageDraw.Draw(canvas)
    # 文字、角色和二维码位于底图上方，替换底图不改变这些图层的位置。
    title = settings["card_title"]
    title_size = 44
    while title_size > 28 and font(title_size).getlength(title) > 828:
        title_size -= 1
    title_width = max(228, font(title_size).getlength(title) + 72)
    draw.rounded_rectangle(
        (540 - title_width / 2, 70, 540 + title_width / 2, 146),
        radius=38,
        fill="#314d3e",
    )
    _center(draw, title, 80 + (44 - title_size) // 2, title_size, "#fffdf4")
    _center(draw, "给可可子一点小小的鼓励", 160, 24, "#647455")

    bubble = (135, 218, 945, 398)
    draw.rounded_rectangle((143, 226, 953, 406), radius=42, fill="#d9e3c5")
    draw.polygon([(646, 384), (718, 384), (677, 438)], fill="#ffffff")
    draw.rounded_rectangle(bubble, radius=42, fill="#ffffff")
    selected, lines, leading = fit_text(settings["bubble_text"], 714, 136)
    y = 308 - len(lines) * leading / 2
    for line in lines:
        draw.text((540, y), line, font=selected, fill="#35483b", anchor="mt")
        y += leading

    # 角色的所有像素限制在二维码有效区域上方；始终保留额外白边。
    draw.rounded_rectangle((246, 714, 846, 1324), radius=42, fill="#cddab7")
    draw.rounded_rectangle(
        (236, 704, 844, 1312), radius=42, fill="#fffef8", outline="#d3b468", width=4
    )
    if qr is not None:
        contained = ImageOps.contain(qr, (520, 520), method=Image.Resampling.NEAREST)
        x = QR_BOX[0] + (520 - contained.width) // 2
        y = QR_BOX[1] + (520 - contained.height) // 2
        # 整个码区保持纯白，二维码按原图等比例嵌入，不裁切、不重新编码。
        draw.rectangle(QR_BOX, fill="white")
        canvas.paste(contained, (x, y))
    else:
        draw.rounded_rectangle(QR_BOX, radius=20, fill="#f3f4ed")
        _center(draw, "上传付款二维码", 974, 34, "#78846e")
        _center(draw, "此处为预览占位，不可付款", 1032, 21, "#929a88")

    character_path = character_path or ASSETS / "keko-feeding.png"
    if character is None and character_path.is_file():
        with Image.open(character_path) as source:
            character = source.convert("RGBA")
            alpha_bbox = character.getchannel("A").getbbox()
            if alpha_bbox:
                character = character.crop(alpha_bbox)
    if character is not None:
        character = ImageOps.contain(
            character.convert("RGBA"), (800, 336), Image.Resampling.LANCZOS
        )
        canvas.paste(
            character,
            ((1080 - character.width) // 2, 736 - character.height),
            character,
        )
    else:
        _center(draw, "可可子模板待生成", 545, 30, "#8b977c")
    footer = settings["footer_text"]
    if footer:
        size = 26
        while size > 18 and font(size).getlength(footer) > 920:
            size -= 1
        _center(draw, footer, 1341, size, "#657454")
    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()
