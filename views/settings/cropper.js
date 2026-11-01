// 只管理选区。实际裁切由后端按原图像素完成，不经过浏览器缩图。
const $ = (id) => document.getElementById(id);
const clamp = (n, low, high) => Math.max(low, Math.min(high, n));

export class ImageCropper {
  constructor() {
    this.dialog = $("crop-dialog");
    this.canvas = $("crop-canvas");
    this.context = this.canvas.getContext("2d");
    this.canvas.addEventListener("pointerdown", (event) => this.down(event));
    this.canvas.addEventListener("pointermove", (event) => this.move(event));
    for (const name of ["pointerup", "pointercancel"]) this.canvas.addEventListener(name, () => {this.drag = null;});
    $("crop-cancel").addEventListener("click", () => this.finish(undefined));
    this.dialog.addEventListener("cancel", (event) => {event.preventDefault(); this.finish(undefined);});
    $("crop-original").addEventListener("click", () => this.finish(null));
    $("crop-apply").addEventListener("click", () => this.finish({...this.box}));
    $("crop-reset").addEventListener("click", () => this.reset());
    $("crop-aspect").addEventListener("change", () => this.preset());
    for (const name of ["x", "y", "width", "height"]) {
      $("crop-" + name).addEventListener("input", () => this.number(name, false));
      $("crop-" + name).addEventListener("change", () => this.number(name));
    }
  }

  async open(info, options) {
    this.info = info;
    this.options = options;
    this.drag = null;
    $("crop-heading").textContent = "裁切" + options.label;
    $("crop-help").textContent = options.help;
    $("crop-recommended").textContent = options.aspectLabel;
    $("crop-original").textContent = "使用整张图片";
    $("crop-source-size").textContent = `原图 ${info.width} × ${info.height} 像素`;
    const image = new Image();
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = () => reject(new Error("图片预览加载失败。"));
      image.src = info.image;
    });
    this.image = image;
    this.scale = Math.min((this.canvas.width - 24) / info.width, (this.canvas.height - 24) / info.height);
    this.offset = {x: (this.canvas.width - info.width * this.scale) / 2, y: (this.canvas.height - info.height * this.scale) / 2};
    this.reset();
    this.dialog.showModal();
    return new Promise((resolve) => {this.resolve = resolve;});
  }

  finish(value) {
    this.dialog.close();
    this.drag = null;
    this.resolve?.(value);
    this.resolve = null;
  }

  ratio() {
    const value = $("crop-aspect").value;
    return value === "recommended" ? this.options.ratio : value === "original" ? this.info.width / this.info.height : 0;
  }

  reset() {
    $("crop-aspect").value = "free";
    this.box = {x: 0, y: 0, width: this.info.width, height: this.info.height};
    this.draw();
  }

  preset() {
    const ratio = this.ratio();
    if (!ratio) return;
    let width = this.info.width, height = this.info.height;
    if (width / height > ratio) width = height * ratio;
    else height = width / ratio;
    this.box = {x: Math.round((this.info.width - width) / 2), y: Math.round((this.info.height - height) / 2), width: Math.round(width), height: Math.round(height)};
    this.normalize();
    this.draw();
  }

  normalize() {
    const b = this.box;
    b.width = clamp(Math.round(b.width), 1, this.info.width);
    b.height = clamp(Math.round(b.height), 1, this.info.height);
    b.x = clamp(Math.round(b.x), 0, this.info.width - b.width);
    b.y = clamp(Math.round(b.y), 0, this.info.height - b.height);
  }

  number(name, commit = true) {
    const value = $("crop-" + name).value;
    const n = Number(value);
    if (!value.trim() || !Number.isFinite(n)) {
      if (commit) this.draw();
      else $("crop-apply").disabled = true;
      return;
    }
    this.box[name] = Math.round(n);
    const ratio = this.ratio();
    if (ratio && name === "width") {
      this.box.width = clamp(this.box.width, 1, Math.min(this.info.width, this.info.height * ratio));
      this.box.height = this.box.width / ratio;
    }
    if (ratio && name === "height") {
      this.box.height = clamp(this.box.height, 1, Math.min(this.info.height, this.info.width / ratio));
      this.box.width = this.box.height * ratio;
    }
    this.normalize();
    this.draw(commit ? null : name);
  }

  point(event) {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: clamp(((event.clientX - rect.left) * this.canvas.width / rect.width - this.offset.x) / this.scale, 0, this.info.width),
      y: clamp(((event.clientY - rect.top) * this.canvas.height / rect.height - this.offset.y) / this.scale, 0, this.info.height),
    };
  }

  down(event) {
    if (event.button !== 0) return;
    event.preventDefault();
    const p = this.point(event), b = this.box;
    const tolerance = 16 / this.scale;
    const corners = [[b.x, b.y], [b.x + b.width, b.y], [b.x, b.y + b.height], [b.x + b.width, b.y + b.height]];
    const corner = corners.findIndex(([x, y]) => Math.hypot(p.x - x, p.y - y) < tolerance);
    if (corner >= 0) {
      const opposite = corners[3 - corner];
      this.drag = {mode: "resize", anchor: {x: opposite[0], y: opposite[1]}};
    } else if (p.x >= b.x && p.x <= b.x + b.width && p.y >= b.y && p.y <= b.y + b.height) {
      this.drag = {mode: "move", start: p, box: {...b}};
    } else {
      this.drag = {mode: "resize", anchor: p};
    }
    this.canvas.setPointerCapture(event.pointerId);
  }

  move(event) {
    if (!this.drag) return;
    const p = this.point(event), d = this.drag;
    if (d.mode === "move") {
      this.box = {...d.box, x: d.box.x + p.x - d.start.x, y: d.box.y + p.y - d.start.y};
    } else {
      const a = d.anchor, sx = p.x >= a.x ? 1 : -1, sy = p.y >= a.y ? 1 : -1;
      const maxW = sx > 0 ? this.info.width - a.x : a.x;
      const maxH = sy > 0 ? this.info.height - a.y : a.y;
      let width = Math.abs(p.x - a.x), height = Math.abs(p.y - a.y);
      const ratio = this.ratio();
      if (ratio) {
        width = Math.max(width, height * ratio);
        height = width / ratio;
        const factor = Math.min(1, maxW / (width || 1), maxH / (height || 1));
        width *= factor; height *= factor;
      }
      this.box = {x: sx > 0 ? a.x : a.x - width, y: sy > 0 ? a.y : a.y - height, width, height};
    }
    this.normalize();
    this.draw();
  }

  draw(editingField = null) {
    const ctx = this.context, w = this.canvas.width, h = this.canvas.height;
    ctx.clearRect(0, 0, w, h);
    for (let y = 0; y < h; y += 16) for (let x = 0; x < w; x += 16) {
      ctx.fillStyle = ((x + y) / 16) % 2 ? "#e4e8e0" : "#f4f6ef";
      ctx.fillRect(x, y, 16, 16);
    }
    const ox = this.offset.x, oy = this.offset.y, s = this.scale, b = this.box;
    ctx.drawImage(this.image, ox, oy, this.info.width * s, this.info.height * s);
    const x = ox + b.x * s, y = oy + b.y * s, bw = b.width * s, bh = b.height * s;
    ctx.fillStyle = "#17241aaa";
    ctx.fillRect(0, 0, w, y); ctx.fillRect(0, y + bh, w, h - y - bh);
    ctx.fillRect(0, y, x, bh); ctx.fillRect(x + bw, y, w - x - bw, bh);
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 2;
    ctx.strokeRect(x, y, bw, bh);
    ctx.strokeStyle = "#ffffff70"; ctx.lineWidth = 1;
    for (const third of [1 / 3, 2 / 3]) {
      ctx.beginPath(); ctx.moveTo(x + bw * third, y); ctx.lineTo(x + bw * third, y + bh); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x, y + bh * third); ctx.lineTo(x + bw, y + bh * third); ctx.stroke();
    }
    ctx.fillStyle = "#fff";
    for (const [cx, cy] of [[x,y], [x+bw,y], [x,y+bh], [x+bw,y+bh]]) ctx.fillRect(cx-5,cy-5,10,10);
    for (const name of ["x", "y", "width", "height"]) {
      if (name !== editingField) $("crop-" + name).value = b[name];
    }
    $("crop-selection-size").textContent = `选区 ${b.width} × ${b.height} 像素`;
    const small = b.width < 80 || b.height < 80;
    $("crop-apply").disabled = small;
    $("crop-size-error").hidden = !small;
  }
}
