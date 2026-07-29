# 桌面客户端 · Web 管理台 · 模块化（Windows + Ubuntu）

## 形态

| 层 | 启动方式 | 说明 |
|----|----------|------|
| **桌面客户端** | `python -m mozilla_manager.client` / `scripts/run_client.*` | **一个本地程序**；负责拉起后端 + 原生窗口 |
| **Web 管理台** | 被客户端内嵌（pywebview） | AdsPower 风格 UI，模块在 `ui/static/js/modules/*` |
| **HTTP API** | 客户端进程内 uvicorn | `api/routes/*` ↔ `modules/*` 1:1 |
| **纯 Web 模式** | `cli serve` / `run_web.sh` | 仅浏览器访问（可选） |

客户端 **不是**「让用户自己去开网页」；网页 UI 是内嵌资源，窗口是桌面程序。

## 目录（便于维护）

```text
app/mozilla_manager/
├── client/                 # 桌面程序（本层）
│   ├── app.py              # 入口编排
│   ├── runtime.py          # 后端进程/线程
│   ├── window_webview.py   # 原生窗（pywebview）
│   ├── window_tk.py        # 降级控制台壳（tk）
│   ├── bridge.py           # JS bridge
│   └── config.py           # data/client/client.json
├── modules/                # 业务域（无 UI）
├── api/routes/             # HTTP 1:1
└── ui/static/js/modules/   # 前端页面模块 1:1
```

改登录态 → 只动 `modules/login_health.py` + 对应 route/js。  
改客户端启动/窗体 → 只动 `client/*`。

## 跨平台

- **Windows**: WebView2（Edge）后端；`scripts\run_client.bat`
- **Ubuntu 桌面**: GTK/WebKit 或 Qt；`bash scripts/run_client.sh`
- **无显示 WSL**: 客户端仍作为程序启动后端；可用 `--tk`（若有 DISPLAY）或 `--no-window` / `--allow-browser`

## 命令

```bash
cd /home/baoge/Mozilla
source .venv/bin/activate
export PYTHONPATH=$PWD/app PLAYWRIGHT_BROWSERS_PATH=$PWD/runtime/browsers

python -m mozilla_manager.client
python -m mozilla_manager.client --tk
python -m mozilla_manager.client --no-window
python -m mozilla_manager.cli client
```
