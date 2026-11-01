"""保持旧版 Pages 与新版 Views 静态入口完全一致。"""

from pathlib import Path
from shutil import copyfile

root = Path(__file__).resolve().parents[1]
for name in ("index.html", "app.js", "style.css", "cropper.js"):
    copyfile(root / "pages/settings" / name, root / "views/settings" / name)
