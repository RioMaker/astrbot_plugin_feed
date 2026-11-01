# 资源说明

`keko-feeding.png`：基于用户于 2026-11-01 提供的五张可可子参考图，使用内置 **imagegen** 生成的透明角色插画。保留浅绿色双马尾、彩虹皇冠和发夹、红橙色眼睛、蓝色耳机、白色水手服及蓝色蝴蝶结。参考图本身未复制进发布包。

该角色插画用于固定模板；付款二维码和可配置文字由插件单独嵌入，不会在运行时调用生成服务。

最终生成提示词（内置工具，`transparent_background=true`）：

> Use case: illustration-story. Asset type: transparent mascot illustration for an AstrBot donation card template. All five inputs are character identity references for the SAME fictional chibi girl, 可可子; they are NOT edit targets. Preserve her exact identifying features: pale pistachio-green long twin-tail hair and bangs, magenta ribbons, small rainbow-striped three-point crown with gold band, rainbow diamond hair clip, large ruby-red eyes with orange lower irises, dark headphones with bright blue rims around her neck, white sailor blouse with coral-red collar, vivid cyan-blue bow, dark navy pleated skirt with yellow waistband. Create ONE polished adorable chibi illustration with clean dark outlines, flat soft cel shading and crisp edges, matching reference 3's character details and reference 5's lively sweet expression. Pose: she is lying comfortably on her tummy across the top edge of an invisible rectangular QR-code panel, chin close to her folded forearms, looking warmly at viewer, body reclining to the right with bent feet lifted playfully behind. Her forearms and hands rest on ONE horizontal baseline at the very bottom of the character; her body, hair, crown and feet stay ABOVE that line. This will be composited just above a real QR code. Composition: a wide horizontal mascot silhouette, about 2:1, entire crown, ribbons, hair, hands and shoes visible with small clear padding, no cropped parts. Genuinely transparent alpha background, no white matte. Generate ONLY the isolated character, no table, no panel, no frame, no QR pattern, no speech bubble, no text, no watermarks, no additional characters or props. Charming friendly grateful mood, modest costume.

`fonts/FeedSans.otf`：基于 [Noto Sans CJK SC](https://github.com/notofonts/noto-cjk) 的字形子集，派生字体命名为 Feed Sans。上游版权信息保留在字体中，使用 [SIL Open Font License 1.1](fonts/OFL.txt)。字体来源为工作区已保存的 NotoSansCJKsc-Regular.otf，保留 U+0020–00FF、U+2000–206F、U+3000–30FF、U+3400–9FFF、U+FF00–FFEF 以及相关布局字形。
