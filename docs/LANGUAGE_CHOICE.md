# 语言选型：Python 3.11+

固定根目录：`/home/baoge/Mozilla`

| 库 | Python 支持 | 备注 |
|---|---|---|
| Camoufox | 官方一等 | Firefox 反检测内核 |
| Playwright | 官方 | Chromium/FF/WebKit 自动化 |
| Patchright | 官方 Python 包 | Chromium 反检测驱动 |
| rebrowser-patches | 浏览器侧补丁 | 产物放 runtime/patches，Python 启动 |

打包：PyInstaller 目录版，runtime 全内置。  
维护：升级只动 `requirements.txt` + `scripts/bootstrap_runtime.sh`。
