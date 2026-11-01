const bridge = window.AstrBotPluginView || window.AstrBotPluginPage;
const $ = (id) => document.getElementById(id);
let savedRevision = "";
let paymentQr = [];
let connected = false;
let busy = false;
let dirty = false;
let editVersion = 0;
let previewSequence = 0;
let timer;
let currentImage = "";

function notice(message, error = false) {
  $("notice").textContent = message;
  $("notice").classList.toggle("error", error);
  $("notice").hidden = !message;
}
function settings() {
  return {enabled: $("enabled").checked, payment_qr: [...paymentQr], bubble_text: $("bubble-text").value, footer_text: $("footer-text").value};
}
function buttons() {
  $("save").disabled = !connected || busy || !dirty;
  $("reload").disabled = !connected || busy;
  $("refresh-preview").disabled = !connected || busy;
  $("remove-qr").disabled = !connected || busy || !paymentQr.length;
  $("qr-file").disabled = !connected || busy;
  $("download").disabled = !currentImage || busy;
  $("save-state").textContent = !connected ? "尚未连接" : busy ? "处理中…" : dirty ? "有未保存的修改" : "已保存";
  $("save-state").classList.toggle("dirty", dirty);
  $("text-count").textContent = `${Array.from($("bubble-text").value).length} / 120`;
  $("qr-state").textContent = paymentQr.length ? "已选择" : "未设置";
  $("qr-state").classList.toggle("ready", !!paymentQr.length);
}
function changed() {
  if (!connected) return;
  dirty = true;
  editVersion++;
  // Any in-flight image belongs to an older draft and must not replace this one.
  previewSequence++;
  $("preview-state").textContent = "文案已修改，正在更新预览…";
  $("download").disabled = true;
  currentImage = "";
  buttons();
  clearTimeout(timer);
  timer = setTimeout(preview, 650);
}
async function preview() {
  if (!connected) return;
  const sequence = ++previewSequence;
  $("preview-state").textContent = "正在合成…";
  try {
    const result = await bridge.apiPost("preview", {settings: settings()});
    if (sequence !== previewSequence) return;
    currentImage = result.image;
    $("preview-image").src = currentImage;
    $("preview-image").hidden = false;
    $("preview-empty").hidden = true;
    $("preview-state").textContent = paymentQr.length ? "与 /投喂 使用相同的合成效果" : "示意预览 · 尚未配置付款二维码";
    buttons();
  } catch (error) {
    if (sequence !== previewSequence) return;
    currentImage = "";
    $("preview-state").textContent = "预览未更新";
    notice(error.message || "预览失败，请重试。", true);
    buttons();
  }
}
function applyState(state) {
  savedRevision = state.revision;
  paymentQr = [...state.settings.payment_qr];
  $("bubble-text").value = state.settings.bubble_text;
  $("footer-text").value = state.settings.footer_text;
  $("enabled").checked = state.settings.enabled;
  $("file-name").textContent = paymentQr.length ? "已使用保存的二维码图片" : "上传一张清晰的收款二维码";
  dirty = false;
  editVersion++;
  buttons();
}
async function reload(force = false) {
  if (dirty && !force) {
    $("confirm-reload").hidden = false;
    notice("有尚未保存的修改。若要丢弃，请点击「放弃修改并载入」。");
    return;
  }
  $("confirm-reload").hidden = true;
  busy = true;
  for (const id of ["bubble-text", "footer-text", "enabled"]) $(id).disabled = true;
  buttons();
  clearTimeout(timer);
  previewSequence++;
  try {
    const state = await bridge.apiGet("settings");
    connected = true;
    applyState(state);
    notice(state.template_ready ? "" : "角色模板缺失，请重新安装完整插件。", !state.template_ready);
    await preview();
  } catch (error) {notice(error.message || "读取配置失败。", true);}
  finally {
    busy = false;
    for (const id of ["bubble-text", "footer-text", "enabled"]) $(id).disabled = !connected;
    buttons();
  }
}
async function upload(file) {
  if (!file || busy || !connected) return;
  if (file.size > 8 * 1024 * 1024) {notice("图片不能超过 8 MB。", true); return;}
  busy = true;
  buttons();
  notice("正在上传二维码…");
  try {
    const result = await bridge.upload("qr/upload", file);
    paymentQr = [result.path];
    $("file-name").textContent = file.name;
    changed();
    notice("二维码已加入预览，保存设置后用于 /投喂。");
  } catch (error) {notice(error.message || "上传失败。", true);}
  finally {busy = false; $("qr-file").value = ""; buttons();}
}
$("save").addEventListener("click", async () => {
  if (busy || !connected) return;
  const version = editVersion;
  const snapshot = settings();
  busy = true;
  buttons();
  try {
    const result = await bridge.apiPost("settings/save", {settings: snapshot, revision: savedRevision});
    savedRevision = result.revision;
    // Preserve edits typed while the save request was in flight.
    if (version === editVersion) dirty = false;
    notice(dirty ? "已保存提交时的设置，新的修改尚未保存。" : "已保存。发送 /投喂 即可查看赞助图片。");
    await preview();
  } catch (error) {notice(error.message || "保存失败。", true);}
  finally {busy = false; buttons();}
});
$("reload").addEventListener("click", () => reload());
$("confirm-reload").addEventListener("click", () => reload(true));
$("refresh-preview").addEventListener("click", () => {clearTimeout(timer); notice(""); preview();});
$("settings-form").addEventListener("submit", (event) => event.preventDefault());
for (const id of ["bubble-text", "footer-text", "enabled"]) $(id).addEventListener("input", changed);
$("qr-file").addEventListener("change", (event) => upload(event.target.files[0]));
$("remove-qr").addEventListener("click", () => {paymentQr = []; $("file-name").textContent = "上传一张清晰的收款二维码"; changed();});
const zone = $("drop-zone");
for (const name of ["dragenter", "dragover"]) zone.addEventListener(name, (event) => {event.preventDefault(); zone.classList.add("dragging");});
for (const name of ["dragleave", "drop"]) zone.addEventListener(name, (event) => {event.preventDefault(); zone.classList.remove("dragging");});
zone.addEventListener("drop", (event) => upload(event.dataTransfer.files[0]));
$("download").addEventListener("click", () => {
  if (!currentImage) return;
  const link = document.createElement("a");
  link.href = currentImage;
  link.download = "可可子-赞助预览.png";
  link.click();
});
window.addEventListener("beforeunload", (event) => {if (dirty) {event.preventDefault(); event.returnValue = "";}});
function theme(context) {document.documentElement.dataset.theme = context?.isDark ? "dark" : "light";}
try {
  if (!bridge) throw new Error("请从 AstrBot 管理面板的「赞助」插件中打开此页面。");
  theme(await bridge.ready());
  bridge.onContext?.(theme);
  await reload();
} catch (error) {notice(error.message, true); buttons();}
