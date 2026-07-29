# 模块划分（Web 管理台 + 业务）

根目录固定：`/home/baoge/Mozilla`

## 总览

```text
app/mozilla_manager/
├── modules/                 # 业务域（无 HTTP）
│   ├── system.py            # boot / health
│   ├── profiles.py          # 环境 CRUD / 启停 / 检测 / 导出
│   ├── groups.py            # 分组聚合
│   ├── proxies.py           # 代理清单
│   ├── subscriptions.py     # 订阅导入 / 节点
│   ├── mihomo_svc.py        # mihomo 进程
│   └── doctor_svc.py        # 诊断
├── api/                     # HTTP 层（FastAPI routers）
│   ├── __init__.py          # create_app()
│   ├── schemas.py
│   └── routes/              # 与 modules 1:1
│       ├── system.py
│       ├── profiles.py
│       ├── groups.py
│       ├── proxies.py
│       ├── subscriptions.py
│       ├── mihomo.py
│       └── doctor.py
├── ui/static/               # 前端管理台
│   ├── index.html           # 壳（布局/导航）
│   ├── css/app.css
│   └── js/
│       ├── core/            # api / state / toast / app shell
│       └── modules/         # 与后端域 1:1 的页面模块
├── web.py                   # 入口：create_app()
├── service.py               # 兼容门面（CLI 可继续用）
└── cli.py                   # 命令行
```

## 约定

1. **改业务逻辑** → 只动 `modules/<域>.py`
2. **改 API 路径/入参** → 只动 `api/routes/<域>.py` + `schemas.py`
3. **改某个页面** → 只动 `ui/static/js/modules/<域>.js`
4. **壳子导航/布局** → `index.html` + `js/core/app.js` + `css/app.css`
5. 禁止跨域互相 import 实现细节；跨域调用走 modules 公开函数

## API 映射

| 前端模块 | API 前缀 | 后端 module |
|---|---|---|
| profiles | `/api/profiles` | `modules.profiles` |
| groups | `/api/groups` | `modules.groups` |
| proxies | `/api/proxies` | `modules.proxies` |
| subscriptions | `/api/subscriptions` `/api/nodes` | `modules.subscriptions` |
| doctor | `/api/doctor` `/api/mihomo` | `doctor_svc` + `mihomo_svc` |


## v2 新增模块

| 域 | 业务 | API | 前端 |
|----|------|-----|------|
| templates | `modules/templates.py` + `env_packs.py` + `fingerprints.py` | `api/routes/templates.py` | 订阅「用于新建」自动推荐 |
| sessions | `modules/sessions.py` | `api/routes/sessions.py` | profiles 行「备份」 |
| browser_only | `network/browser_only.py` | launch 内置 | — |


## v4 新增模块

| 域 | 业务 | API |
|----|------|-----|
| cookies | `modules/cookies.py` | `/api/cookies/*` |
| login_health | `modules/login_health.py` | `/api/login-health/*` |
| timetravel | `modules/timetravel.py` | `/api/timetravel/*` |
| failover | `modules/failover.py` + `network/mihomo_api.py` | `/api/failover/*` |
| anti_leak | `network/anti_leak.py` | `/api/privacy/*` |
| migrate | tab 迁移 | `/api/migrate` |
| extension | `runtime/extensions/mozilla-helper` | 右键菜单 |
| incremental | `snapshots.export_profile_zip_incremental` | `export-incremental` |

## v5 模块

| 模块 | 路径 | 职责 |
|------|------|------|
| node_store | `network/node_store.py` | runtime/nodes 本地节点库、active、导出/导入、迁移 |
| subscription | `network/subscription.py` | 拉取订阅 → 写入 node_store + legacy 镜像 |
| subscriptions | `modules/subscriptions.py` | 业务：switch/export/active/runtime |
| turnstile | `modules/turnstile.py` | CF 盾适配 Playwright + harvester vendor |
| API subs | `api/routes/subscriptions.py` | `/api/subscriptions/*` `/api/nodes-raw` |
| API CF | `api/routes/turnstile.py` | `/api/turnstile/*` |
| UI subs | `ui/static/js/modules/subscriptions.js` | 切换/导出/本地导入/CF 操作 |

约束：所有节点文件只写 `ROOT/runtime/nodes/**` 与兼容镜像 `ROOT/data/nodes/**`。

## v6 模块

| 模块 | 路径 | 职责 |
|------|------|------|
| stealth.seed | `stealth/seed.py` | Profile 稳定 PRNG |
| stealth.bundle | `stealth/bundle.py` | 24+ 维 bundle 生成/落盘 |
| stealth.init_script | `stealth/init_script.py` | 浏览器注入脚本 |
| stealth.tls_ja | `stealth/tls_ja.py` | JA3/JA4 人格 + mihomo fingerprint |
| stealth.entropy | `stealth/entropy.py` | 熵值/碰撞率 |
| net_quality | `network/net_quality.py` | 丢包/稳定性/归属地一致性 |
| stealth_svc | `modules/stealth_svc.py` | 业务封装 |
| API | `api/routes/stealth.py` | `/api/stealth/*` |


## v7 模块

| 模块 | 路径 | 职责 |
|------|------|------|
| env_packs_global | `env_packs_global.py` | ~92 额外国家模板，与默认包合并 |
| batch_svc | `modules/batch_svc.py` | 按国批量建档 + 城市/viewport/语言/指纹漂移 |
| totp_svc | `modules/totp_svc.py` | TOTP 账户 CRUD + 一键填充脚本（无 pyotp） |
| rpa.store | `rpa/store.py` | 工作流 JSON → `data/rpa/workflows/` |
| rpa.runner | `rpa/runner.py` | 对 profile 执行步骤（含 totp） |
| rpa.scheduler | `rpa/scheduler.py` | interval/daily 守护线程 |
| diagnose | `network/diagnose.py` | 代理/DNS/WebRTC/IP/质量一键报告 |
| transfer_svc | `modules/transfer_svc.py` | 跨机迁移 zip 导出/导入 |
| media_fake | `modules/media_fake.py` | 虚拟 cam/mic 开关 + init script |
| API batch/rpa/totp/diagnose/transfer/media | `api/routes/*` | 与上表 1:1 |
| UI tools | `ui/static/js/modules/tools.js` | 导航「v7 工具箱」 |

数据目录：`data/rpa/` · `data/totp/` · `data/exports/migrate/` · `data/media/virtual/` · `logs/rpa|diagnose/`

## v8 模块

| 模块 | 路径 | 职责 |
|------|------|------|
| rpa.recorder | `rpa/recorder.py` | 运行中浏览器事件录制 → 工作流 |
| jobs_svc | `modules/jobs_svc.py` | 后台任务 + stale 回收 |
| tags_svc | `modules/tags_svc.py` | profile.meta.tags |
| ops_svc | `modules/ops_svc.py` | dashboard / history / bulk diagnose / summary |
| API | `api/routes/{recorder,jobs,tags,ops}.py` | 1:1 |
| UI | profiles/tools/create_modal/app | 行内操作 · 工具箱 · 112 国家 |

## v9 模块

| 模块 | 路径 | 职责 |
|------|------|------|
| notify_svc | `modules/notify_svc.py` | 通知中心 data/notices |
| lock_svc | `modules/lock_svc.py` | 环境锁；拦截 launch/delete |
| watchdog_svc | `modules/watchdog_svc.py` | 登录/诊断/质量巡检调度 |
| jobs progress | `modules/jobs_svc.set_progress` | 任务进度百分比 |
| recorder.timeline | `rpa/recorder.py` | 录制事件时间线 |
| API | notify/locks/watchdogs/audit | 1:1 |
| UI | tools + profiles + side badge | 巡检/通知/锁 |

## v10 模块

| 模块 | 路径 | 职责 |
|------|------|------|
| machine_svc | `modules/machine_svc.py` | 机器 ID / 名称 |
| fleet_svc | `modules/fleet_svc.py` | 多机同步 pack 导出导入 |
| vault_svc | `modules/vault_svc.py` | 本地密钥库 |
| report_svc | `modules/report_svc.py` | 运维 JSON/HTML 报表 |
| backup_svc | `modules/backup_svc.py` | 整机备份 + 定时 |
| ws_hub | `api/ws_hub.py` | `/ws/jobs` 进度推送 |
| API | fleet/vault/reports/backup | 1:1 |

## 桌面客户端（client）

| 模块 | 路径 | 职责 |
|------|------|------|
| app | `client/app.py` | 程序入口编排 |
| runtime | `client/runtime.py` | 进程内启动/停止 FastAPI |
| window_webview | `client/window_webview.py` | 原生窗口内嵌管理台 |
| window_tk | `client/window_tk.py` | 无 webview 时的桌面壳 |
| bridge | `client/bridge.py` | 页内 JS API |
| config | `client/config.py` | `data/client/client.json` |

与 Web 关系：客户端 = 壳；`ui/static/js/modules/*` = 页面；`api/routes/*` = 接口；`modules/*` = 业务。
