# rebrowser-patches 接入说明

上游：https://github.com/rebrowser/rebrowser-patches

rebrowser-patches 是 **Playwright/Puppeteer 驱动补丁源**，不是独立浏览器品牌。

## 本项目约定（ROOT 内置）

| 产物 | 路径 |
|---|---|
| 补丁源码 | `runtime/patches/rebrowser-patches/` |
| Python 驱动（已打补丁的 drop-in） | pip `rebrowser-playwright`（`.venv`） |
| 可选自定义 Chromium 二进制 | `runtime/patches/rebrowser/chrome` |

## 选用

```bash
python -m mozilla_manager.cli create -n x --engine pw_chromium --patch rebrowser
# 或 Web UI 新建 → 补丁 = rebrowser
```

启动器优先：
1. `from rebrowser_playwright.sync_api import sync_playwright`
2. 若存在 `runtime/patches/rebrowser/chrome` 则 `executable_path` 指向它
3. 否则使用 `PLAYWRIGHT_BROWSERS_PATH` 下已安装的 chromium

## 与 Patchright 的区别

| | Patchright | rebrowser |
|---|---|---|
| 形态 | pip 驱动替换 | 补丁源 + rebrowser-playwright 驱动 |
| 选用 | `--patch patchright` | `--patch rebrowser` |
| 内核 | Chromium | Chromium |

二者可在不同 Profile 上自由搭配。
