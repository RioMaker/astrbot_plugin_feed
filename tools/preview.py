"""本地开发预览：仅监听回环地址，使用测试二维码，不连接 AstrBot。"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from astrbot_plugin_feed.config import DEFAULTS, FeedError  # noqa: E402
from astrbot_plugin_feed.service import FeedService  # noqa: E402

DATA = ROOT / ".preview" / "data"
DATA.mkdir(parents=True, exist_ok=True)


class PreviewConfig(dict):
    def save_config(self):
        (DATA / "settings.json").write_text(
            json.dumps(self, ensure_ascii=False), encoding="utf-8"
        )


config_path = DATA / "settings.json"
config = PreviewConfig(
    json.loads(config_path.read_text(encoding="utf-8"))
    if config_path.exists()
    else {**DEFAULTS, "footer_text": "示例二维码 · 不可付款"}
)
service = FeedService(config, DATA)
loop = asyncio.new_event_loop()

BRIDGE = """<script>
window.AstrBotPluginView = {
  ready:async()=>({isDark:false}),onContext:()=>()=>{},
  async call(endpoint,body){
    const r=await fetch('/dev/'+endpoint,{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body||{})});
    const data=await r.json();if(!r.ok)throw new Error(data.message);return data;
  },
  apiGet(endpoint){return this.call(endpoint)},
  apiPost(endpoint,body){return this.call(endpoint,body)},
  async upload(endpoint,file){
    const bytes=new Uint8Array(await file.arrayBuffer());let text='';
    for(let i=0;i<bytes.length;i+=8192){
      text+=String.fromCharCode(...bytes.subarray(i,i+8192));
    }
    return this.call(endpoint,{base64:btoa(text)});
  }
};
</script>"""


class Handler(BaseHTTPRequestHandler):
    def send(self, status, content, mime="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        files = {
            "/": "index.html",
            "/index.html": "index.html",
            "/app.js": "app.js",
            "/cropper.js": "cropper.js",
            "/style.css": "style.css",
        }
        filename = files.get(self.path.split("?", 1)[0])
        if not filename:
            self.send(404, b"not found", "text/plain")
            return
        text = (ROOT / "pages" / "settings" / filename).read_text(encoding="utf-8")
        if filename == "index.html":
            text = text.replace("</head>", BRIDGE + "</head>")
        mime = {
            "index.html": "text/html; charset=utf-8",
            "app.js": "text/javascript; charset=utf-8",
            "cropper.js": "text/javascript; charset=utf-8",
            "style.css": "text/css; charset=utf-8",
        }[filename]
        self.send(200, text.encode(), mime)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 <= length <= 12 * 1024 * 1024:
                raise FeedError("请求过大", 413)
            data = json.loads(self.rfile.read(length))
            if self.path == "/dev/settings":
                result = service.state()
            elif self.path == "/dev/settings/save":
                result = loop.run_until_complete(
                    service.save(data["settings"], data["revision"])
                )
            elif self.path == "/dev/preview":
                image = loop.run_until_complete(service.preview(data["settings"]))
                result = {
                    "image": "data:image/png;base64," + base64.b64encode(image).decode()
                }
            elif self.path in {
                "/dev/qr/upload",
                "/dev/character/upload",
                "/dev/background/upload",
            }:
                kind = self.path.split("/")[2]
                path = loop.run_until_complete(
                    service.upload(
                        base64.b64decode(data["base64"], validate=True), kind
                    )
                )
                result = {"path": path}
            elif self.path == "/dev/images/read":
                result = loop.run_until_complete(
                    service.image_info(data.get("kind"), data.get("path"))
                )
            elif self.path == "/dev/images/crop":
                result = {
                    "path": loop.run_until_complete(
                        service.crop(
                            data.get("kind"), data.get("path"), data.get("box")
                        )
                    )
                }
            else:
                raise FeedError("Not found", 404)
            self.send(200, json.dumps(result, ensure_ascii=False).encode())
        except FeedError as error:
            self.send(
                error.status,
                json.dumps({"message": str(error)}, ensure_ascii=False).encode(),
            )


if __name__ == "__main__":
    print("Local preview: http://127.0.0.1:8769", flush=True)
    try:
        HTTPServer(("127.0.0.1", 8769), Handler).serve_forever()
    finally:
        loop.close()
