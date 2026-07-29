# 架构

```text
Mozilla/                          ← 唯一允许产生文件的根
├── app/mozilla_manager/          ← Python 业务
│   ├── modules/                  ← 功能域（profiles/groups/proxies/subs/mihomo/doctor）
│   ├── api/routes/               ← FastAPI 路由，与 modules 1:1
│   ├── ui/static/js/modules/     ← 前端页面模块，与后端域 1:1
│   ├── cli.py / web.py / service.py  ← 薄入口与兼容门面
│   ├── engines/                  ← camoufox | playwright | patchright
│   ├── network/                  ← mihomo / socks5 底层
│   └── paths.py                  ← 全部路径锁死在 ROOT
├── runtime/
│   ├── browsers/                 ← Playwright/Patchright 浏览器
│   ├── mihomo/                   ← 内核二进制
│   └── patches/                  ← rebrowser 等补丁产物
├── data/profiles/<id>/           ← 每配置独立 user_data_dir
├── data/nodes/                   ← 订阅与 mihomo 配置
├── logs/ tmp/ dist/
└── scripts/bootstrap_runtime.*   ← 一键内置依赖
```

## 引擎矩阵

| 用户选择 | 实际启动 |
|---|---|
| Firefox 反检测 | Camoufox |
| Chromium 原版 | Playwright Chromium |
| Chromium + Patchright | `patchright` 驱动 |
| Chromium + rebrowser | Playwright + `runtime/patches` 中的 patched browser |

## 网络

- 系统代理不改
- 每个 Profile 可绑：直连 / socks5 / 本地 mihomo 端口
- 启动时注入 timezone / locale / geolocation / UA / viewport


模块维护约定见 [MODULES.md](MODULES.md)。

## 桌面客户端 + Web 管理台（跨平台）

```text
┌─────────────────────────────────────────────┐
│  Desktop Client  (python -m mozilla_manager.client)
│  Windows: run_client.bat / WebView2
│  Ubuntu:  run_client.sh  / GTK·Qt webview
│    • runtime.py  进程内 uvicorn + create_app()
│    • window_*    原生窗口（不是“用户去开浏览器”）
└─────────────────┬───────────────────────────┘
                  │ http://127.0.0.1:17888
┌─────────────────▼───────────────────────────┐
│  Web Admin  ui/static/js/modules/*          │
│  API        api/routes/*  1:1               │
│  Domain     modules/*                       │
│  ROOT lock  /home/baoge/Mozilla             │
└─────────────────────────────────────────────┘
```

纯 `cli serve` 仍可用；日常推荐客户端程序入口。
