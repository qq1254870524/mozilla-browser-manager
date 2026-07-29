# 断点续传下载

「下载依赖」对三大组件全部支持 **多镜像 + 断点续传**：

| 组件 | 脚本 | 续传文件 |
|------|------|----------|
| Chromium | `scripts/fetch_chromium.py` | `tmp/playwright-*.zip.part` |
| Camoufox | `scripts/fetch_camoufox.py` | `tmp/camoufox-*.zip.part` |
| mihomo | `scripts/install_all_deps.py` / netfetch | `runtime/mihomo/mihomo.download.*.part` |

公共库：`scripts/netfetch.py`

中断后再次双击 **下载依赖.bat** 即可从断点继续，无需从头下载。
