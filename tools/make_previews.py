"""生成明确标注的测试卡片；不包含真实收款信息。"""

import asyncio
import io
import sys
from pathlib import Path

import qrcode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_feed.config import DEFAULTS  # noqa: E402
from astrbot_plugin_feed.render import render_card  # noqa: E402

output = ROOT / "output"
output.mkdir(exist_ok=True)
qr = qrcode.make(
    "https://example.invalid/feed-preview/TEST-ONLY", box_size=12, border=4
).convert("RGB")
qr.save(output / "test-qr.png")
(output / "card-demo.png").write_bytes(
    render_card({**DEFAULTS, "footer_text": "示例二维码 · 不可付款"}, qr)
)
(output / "card-unconfigured.png").write_bytes(render_card(DEFAULTS, None))

if "--seed" in sys.argv:
    from preview import config, service

    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    path = asyncio.run(service.upload(buffer.getvalue()))
    config["payment_qr"] = [path]
    config["footer_text"] = "示例二维码 · 不可付款"
    config.save_config()
print("Preview images written to output/")
