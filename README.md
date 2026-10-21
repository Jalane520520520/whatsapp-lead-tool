# whatsapp-lead-tool

Windows 桌面软件：输入产品关键词和国家 → 谷歌地图逐格找商家 → 查官网上的 WhatsApp → （登录后）验证电话是否开通 WhatsApp → 每个「关键词 + 国家」一张 Excel，越抓越多。只查号，不发消息。

- `launcher.py` 启动器：启动时向本仓库的最新 Release 要 `app.zip`（热更新），失败就用本机已有版本。
- `app/` 窗口和流程；`maps/` 谷歌地图（gosom）；`web/` 官网查找（crawl4ai）；`wa_check/` WhatsApp 验证（Baileys，只读）。
- `build/` Windows 打包；`.github/workflows/build.yml` 推 `v*` 标签后自动打包、安装、真跑 1 格，通过才发布。

发新版本：改 `VERSION` → 提交 → 打同名标签 `vX.Y.Z` 推上来。
