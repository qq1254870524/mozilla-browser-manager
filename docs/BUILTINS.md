# 内置内核与补丁

全部落在 `/home/baoge/Mozilla`，禁止写到其他盘/HOME（Camoufox 通过 `XDG_CACHE_HOME=$ROOT/runtime/cache` 锁定）。

## 2 种内核

| 内核 | 上游 | 本机位置 | 选用 |
|---|---|---|---|
| **Playwright Chromium** | https://github.com/microsoft/playwright | `runtime/browsers/chromium-*` | `--engine pw_chromium --patch none` |
| **Camoufox (Firefox)** | https://github.com/daijro/camoufox | `runtime/cache/camoufox/browsers/...` | `--engine camoufox` |

## 2 种可自由搭配的补丁（仅 Chromium 引擎）

| 补丁 | 上游 | 本机位置 | 选用 |
|---|---|---|---|
| **Patchright** | https://github.com/Kaliiiiiiiiii-Vinyzu/patchright | pip `patchright` + `runtime/browsers` | `--engine pw_chromium --patch patchright` |
| **rebrowser-patches** | https://github.com/rebrowser/rebrowser-patches | 源码 `runtime/patches/rebrowser-patches/` + pip `rebrowser-playwright` | `--engine pw_chromium --patch rebrowser` |

> rebrowser-patches 是对 Playwright/Puppeteer **驱动层** 的补丁源；Python 侧用官方 drop-in 包 [rebrowser-playwright](https://pypi.org/project/rebrowser-playwright/)（已把补丁打进驱动）。可选自定义 chromium 二进制可放 `runtime/patches/rebrowser/chrome`。

## 下载/更新

```bash
cd /home/baoge/Mozilla
bash scripts/bootstrap_runtime.sh
# 或分步：
source .venv/bin/activate
export PLAYWRIGHT_BROWSERS_PATH=$PWD/runtime/browsers
export XDG_CACHE_HOME=$PWD/runtime/cache
python -m playwright install chromium
python -m patchright install chromium
python -m camoufox fetch
python -m rebrowser_playwright install chromium
```

## 验证

```bash
export PYTHONPATH=$PWD/app
python -m mozilla_manager.cli doctor
python -m mozilla_manager.cli engines
```
