# 赞助 · astrbot_plugin_feed

发送 `/投喂`，返回一张可可子趴在付款二维码框上的赞助卡片。二维码、气泡文案和下方说明都可以在 AstrBot 中设置；不需要调用模型或配置 API Key。

## 安装

本项目是独立插件仓库。将插件文件放到 AstrBot 的 `data/plugins/astrbot_plugin_feed/`，安装 `requirements.txt` 中的依赖，然后重载插件。尚未创建远程仓库，`metadata.yaml` 的 `repo` 留空，不提供虚构的安装地址。

要求 Python 3.10+、AstrBot 4.13.0+。原生文件上传配置需要 AstrBot 4.13.0+；自定义设置页面还需要该 AstrBot 版本提供插件 Pages / Views、Bridge、`astrbot.api.web` 和 `register_web_api`。缺少页面接口时，普通配置及 `/投喂` 仍可使用。

## 配置和使用

1. 登录 AstrBot 管理面板，打开插件 **「赞助」**。
2. 打开 `settings` 可视化视图（部分版本称为 Pages）。
3. 上传一张收款二维码，输入气泡文字，查看右侧合成预览。
4. 点击 **保存设置**。在聊天中发送 `/投喂` 即可得到成图。

也可以在 AstrBot 的普通插件配置中上传 `payment_qr` 文件、修改 `bubble_text`，与可视化页面共用同一份配置。

| 配置 | 说明 |
| --- | --- |
| `enabled` | 是否响应投喂指令，默认开启 |
| `payment_qr` | 一张 PNG / JPG / WebP 付款二维码图片；初始为空 |
| `bubble_text` | 气泡文字，最多 120 字、4 个手动分段，自动换行与缩小字号 |
| `footer_text` | 二维码下方说明，最多 32 字，可留空 |

页面上传只更新草稿，**保存后才用于聊天**。预览与聊天共用同一份渲染代码。两个页面同时编辑时，较旧页面的保存会提示重新载入，避免静默覆盖。

未配置二维码时，页面显示明确的占位提示，聊天返回配置提示，不发送虚假的付款码。文字超出气泡可容纳范围时会提示精简内容。字体包含常用中文、拉丁字母、日文和标点；部分 emoji / 生僻字可能缺字，建议在预览中确认。

## 图片与数据

- 输出为 1080 × 1440 PNG，角色来自用户提供的可可子参考图，由 imagegen 生成，气泡文字由程序绘制。
- 收款码以原图完整等比例嵌入，不裁切、不重新编码；角色图层不会覆盖二维码有效区域，额外保留白边。
- 推荐上传清晰的正方形收款码。支持完整付款卡截图，但较大的外围留白、文字会占用展示空间。
- 单张图片最多 8 MB、1600 万像素、最长边 6000；不接受动画和 SVG。
- 上传文件存入 `data/plugin_data/astrbot_plugin_feed/files/payment_qr/`，不会随插件代码更新覆盖。
- 页面移除二维码仅取消使用，不删除已上传的文件。未保存的上传文件也会保留，可在 AstrBot 原生文件配置中管理。
- 所有管理接口要求 AstrBot Dashboard 身份；网页通过官方 Bridge 访问。插件运行时不向外部服务上传二维码。
- 插件只展示收款图片，不校验到账、不处理交易，也不附带积分或奖励逻辑。

## 开发与验证

```bash
python -m pip install -r requirements-dev.txt
python tools/sync_pages.py
ruff format .
ruff check .
python -m pytest -q
python tools/preview.py
```

本地预览地址为 `http://127.0.0.1:8769`，仅监听本机回环接口，使用独立 `.preview/data/` 配置。这个开发预览使用模拟 Bridge，不等同于真实 AstrBot 集成。`pages/settings/` 是页面源文件；修改后运行同步脚本，将其复制到新版入口 `views/settings/`。

测试涵盖二维码嵌入前后解码、缩小后解码、图层遮挡、长文案、原生文件配置、草稿与保存、配置冲突、并发上传、命令发送与管理身份检查。真实 QQ / OneBot 发送与实际付款二维码，需要在安装环境中验证。

接口实现依据 [AstrBot 插件配置](https://docs.astrbot.app/dev/star/guides/plugin-config.html)、[插件可视化视图](https://docs.astrbot.app/dev/star/guides/plugin-pages.html) 和 [插件存储](https://docs.astrbot.app/dev/star/guides/storage.html)，核对日期为 2026-11-01。参考了本工作区 Image Generator 插件的 Dashboard 身份校验与双入口兼容方式，相关项目为 [astrbot_plugin_img_gener](https://github.com/RioMaker/astrbot_plugin_img_gener)；本插件的业务逻辑独立实现。

角色与字体来源、生成提示词见 [assets/README.md](assets/README.md)。
