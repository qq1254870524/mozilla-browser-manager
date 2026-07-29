# 产品形态推进状态

根目录：`/home/baoge/Mozilla`

## v10.1 细节增强 + 全量合规核对 ✅（2026-07-29）

目标：增强现有功能细节，仔细核对 v1–v10 是否都满足条件。

### 增强项

| # | 项 | 说明 |
|---|---|---|
| 1 | Camoufox 引擎对齐 Chromium | cookie 预注入、标签页记忆/恢复、WebRTC prefs、DoH(TRR)、stealth/virtual media、CF auto-pass |
| 2 | launch 自动重绑 UI | 行内「重绑 / 关重绑」、启动 toast 显示 `launch_rebind` |
| 3 | 隐私 / Cookie 行内操作 | WebRTC+DoH 设置；Cookie import/export |
| 4 | Profile meta 回填 | 旧环境补齐 `auto_rebind_on_launch` / webrtc / doh 等；`backfill-meta` |
| 5 | list/get  enrichment | `privacy` / `isolation` / `auto_rebind_on_launch` / `last_launch_rebind` |
| 6 | 合规审计器 | `modules/compliance.py` → CLI `compliance` / API `GET /api/system/compliance` |
| 7 | 版本 | `1.10.1-v10.1` |

### 用户硬性条件（再次确认）

| 条件 | 状态 |
|---|---|
| 每个配置 = 独立 persistent context / user-data-dir | ✅ `data/profiles/<id>/` |
| 独立 CRUD / 复用 / 删除 | ✅ |
| 订阅节点 + mihomo + socks5 | ✅ |
| 每浏览器不同出口（独立 mihomo_port / socks） | ✅ |
| 按 IP 绑定 timezone/locale/geo/UA/viewport/权限 | ✅ |
| 每次 launch 按出口 IP 自动重绑 tz/locale/geo | ✅ 默认开，可关 |
| 仅浏览器走代理，不改系统代理、不写 HOME | ✅ |
| 跨平台 Windows + Ubuntu；客户端是程序不是网页 | ✅ `mozilla_manager.client` |
| 模块化 Web 管理台 + 客户端 | ✅ modules / api/routes / ui modules |
| ROOT 锁定仅 `/home/baoge/Mozilla` | ✅ `paths.safe_resolve` |

### 合规命令

```bash
cd /home/baoge/Mozilla && source .venv/bin/activate
export PYTHONPATH=$PWD/app PLAYWRIGHT_BROWSERS_PATH=$PWD/runtime/browsers XDG_CACHE_HOME=$PWD/runtime/cache
python -m mozilla_manager.cli compliance
python -m mozilla_manager.cli backfill-meta
# Web：系统诊断页 →「v1–v10 合规核对」
```

最新结果：`tmp/compliance_latest.json` → **86/86 通过**。

---

## v1–v10 ✅（2026-07-28）

### v4 验收

| # | 项 | 状态 | 验证 |
|---|---|---|---|
| 1 | Cookie JSON/Base64 导入导出 + 启动前注入 | ✅ | `cookie-import/export`；launch `inject_cookies_to_context`；禁止脱敏 |
| 2 | 登录态健康巡检 +「需重登」标签 | ✅ | `login-watch` / `login-check`；`meta.need_relogin` + `logs/login_health_*.json` |
| 3 | 环境快照时间旅行 | ✅ | `tt-create/list/rollback`；`data/exports/timetravel/<id>/<ts>/` |
| 4 | 节点故障自动切换（不重启浏览器） | ✅ | mihomo API `switch` 204；`failover` 同国候补 + 重绑 env |
| 5 | 节点延迟测速与按国优选 | ✅ | `speedtest` + `nodes-preferred --country JP` |
| 6 | WebRTC 防漏 disable/spoof | ✅ | `privacy-set --webrtc`；chromium args + init script |
| 7 | DNS DoH 防泄漏 | ✅ | `--dns-over-https-mode=secure` + template |
| 8 | 差异/增量导出 | ✅ | `export-incr` → `*_incr_*.zip` |
| 9 | 标签页分组记忆 | ✅ | stop 写入 `meta.tabs` + `tab_groups[last]`；launch 自动打开 |
| 10 | 右键菜单扩展 | ✅ | `runtime/extensions/mozilla-helper`（切节点/迁移/快照/failover） |

### 实测摘要

- Cookie 导入 2 条 → Base64 往返 → launch 注入  
- 时间旅行 live 快照含 cookies+tabs；rollback 恢复  
- mihomo 热切换：`🇯🇵日本高速02|CTCU|0.5x` status **204**，`now` 已变  
- stop 后 tabs=`https://example.com/`，tab_groups.last 保留  
- privacy：`webrtc=spoof` `doh=secure`  
- 增量 zip：`data/exports/v3-jp-9ae997_incr_*.zip`  
- 扩展：`mozilla-helper` 已可 `ext-set`  

### v4 命令

```bash
cd /home/baoge/Mozilla && source .venv/bin/activate
export PYTHONPATH=$PWD/app PLAYWRIGHT_BROWSERS_PATH=$PWD/runtime/browsers XDG_CACHE_HOME=$PWD/runtime/cache

python -m mozilla_manager.cli cookie-import <id> --data '[{"name":"a","value":"b","domain":".x.com"}]'
python -m mozilla_manager.cli cookie-export <id> --fmt base64
python -m mozilla_manager.cli login-watch <id> --urls 'https://site/account'
python -m mozilla_manager.cli login-check <id>
python -m mozilla_manager.cli tt-create <id> --label before-risk
python -m mozilla_manager.cli tt-rollback <id> --ts <TS>
python -m mozilla_manager.cli node-switch <id> --node '🇯🇵日本高速02|CTCU|0.5x'
python -m mozilla_manager.cli failover <id>
python -m mozilla_manager.cli privacy-set <id> --webrtc spoof --doh secure
python -m mozilla_manager.cli export-incr <id>
python -m mozilla_manager.cli nodes-preferred --country JP
python -m mozilla_manager.cli ext-set <id> --ids mozilla-helper
python -m mozilla_manager.cli serve
```

### v4 API

- `POST /api/cookies/profiles/{id}/import|export`
- `POST /api/login-health/profiles/{id}/watch|check` · `POST /api/login-health/check-due`
- `GET/POST /api/timetravel/profiles/{id}` · `POST .../rollback`
- `GET /api/failover/profiles/{id}/candidates` · `POST .../switch|auto`
- `GET/POST /api/privacy/profiles/{id}`
- `POST /api/migrate`
- `POST /api/profiles/{id}/export-incremental`
- `GET /api/nodes/preferred`

Web：http://127.0.0.1:17888


---

## v5 ✅ · runtime/nodes + 订阅切换/导出 + CF Turnstile（2026-07-28）

### v5 验收

| # | 项 | 状态 | 验证 |
|---|---|---|---|
| 1 | 节点本地库 `runtime/nodes/subs/<name>/` | ✅ | meta/clash/nodes/raw 全量落盘，禁止脱敏 |
| 2 | 导入/导出订阅全部节点 | ✅ | `sub-export --fmt zip|json|yaml|jsonl`；UI 导出 |
| 3 | 切换当前订阅 | ✅ | `active.json` + `sub-switch` / API `/switch` |
| 4 | 内置 CF Turnstile harvester | ✅ | `runtime/vendors/turnstile-harvester1`；`turnstile-solve` |
| 5 | legacy → runtime 迁移 | ✅ | boot/`nodes-migrate`；失败保留旧表 |
| 6 | mihomo 读 runtime clash | ✅ | `node_store.load_clash` |
| 7 | Web UI 订阅卡片切换/导出/CF | ✅ | 订阅页 v5 toolbar |

### 目录

```
runtime/nodes/
  active.json
  subs/<name>/{meta.json,clash.yaml,nodes.json,nodes.jsonl,raw.bin,raw.txt}
  exports/sub_<name>_<ts>.zip|json|yaml|jsonl
  mihomo/mihomo-<port>.yaml
runtime/vendors/turnstile-harvester1/
```

### v5 命令

```bash
cd /home/baoge/Mozilla && source .venv/bin/activate
export PYTHONPATH=$PWD/app PLAYWRIGHT_BROWSERS_PATH=$PWD/runtime/browsers XDG_CACHE_HOME=$PWD/runtime/cache

python -m mozilla_manager.cli nodes-migrate
python -m mozilla_manager.cli sub-active
python -m mozilla_manager.cli sub-switch default
python -m mozilla_manager.cli sub-export --name default --fmt zip
python -m mozilla_manager.cli sub-import-file --path runtime/nodes/exports/xxx.zip --name imported
python -m mozilla_manager.cli turnstile-vendor
python -m mozilla_manager.cli turnstile-solve <profile_id> --url 'https://example.com' --headless
python -m mozilla_manager.cli doctor
```

### API

- `GET  /api/subscriptions` `/active` `/runtime`
- `POST /api/subscriptions/import` `/switch` `/export` `/import-file` `/refresh`
- `GET  /api/nodes-raw?full=`
- `GET  /api/turnstile/vendor`
- `POST /api/turnstile/profiles/{id}/solve`

### 说明

- Profile 启动可选 `meta.auto_cf=true` 自动尝试过 CF（Chromium 路径）。
- 订阅真相源：`runtime/nodes/subs/<name>/`；`data/nodes/sub_*` 仍作兼容镜像。
- 导出 **禁止脱敏**（`redacted: false`）。

---

## v6 ✅ · TLS/JA3/JA4 + 24维指纹 + 网络质量 + 强制DoH（2026-07-28）

### v6 验收

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| 1 | TLS/JA3/JA4 人格 | ✅ | `stealth/tls_ja.py` 8 套人格；mihomo `client-fingerprint` |
| 2 | 24+ 核心维度伪装 | ✅ | canvas/webgl/audio/fonts/smbios/cpu/disk/… → `stealth.json` |
| 3 | 熵值 ≥138 bit | ✅ | `estimate_entropy_bits` 理论熵 + profile seed 128bit |
| 4 | 核心维重复率 ≤0.004% | ✅ | `collision_stats` / `stealth-collision` |
| 5 | GPU/驱动深度伪装 | ✅ | renderer + driver_version unmasked |
| 6 | AudioContext 噪声/设备 | ✅ | 固定 persona + noise_scale |
| 7 | hardwareConcurrency | ✅ | 稳定抖动 4–20 |
| 8 | 反自动化 API | ✅ | webdriver/chrome.runtime/plugins |
| 9 | Profile 固定噪点 | ✅ | SHA256(profile_id) StableRNG，跨 Profile 不相关 |
| 10 | 丢包/稳定性/归属地 | ✅ | `net_quality` + `geo_consistency` |
| 11 | 强制 DoH + 自定义 | ✅ | multi-template + `doh_servers` |
| 12 | 启动校验 IP↔tz/locale | ✅ | preflight geo；`geo_match_strict` 可硬拦截 |

### 真相源

`data/profiles/<id>/stealth.json` — 生成后固定，除非 `stealth-regen`。

### 命令

```bash
python -m mozilla_manager.cli stealth-show <id>
python -m mozilla_manager.cli stealth-regen <id> --tls chrome-131-win
python -m mozilla_manager.cli stealth-tls <id> chrome-131-win
python -m mozilla_manager.cli stealth-doh <id> --template https://dns.google/dns-query --servers 'https://dns.google/dns-query https://cloudflare-dns.com/dns-query'
python -m mozilla_manager.cli stealth-entropy [id]
python -m mozilla_manager.cli stealth-collision --limit 30
python -m mozilla_manager.cli tls-profiles
python -m mozilla_manager.cli net-quality <id> --samples 5
python -m mozilla_manager.cli geo-strict <id> --enable
```

### API

- `GET  /api/stealth/tls-profiles|entropy|collision`
- `GET  /api/stealth/profiles/{id}`
- `POST /api/stealth/profiles/{id}/regenerate|tls|doh|net-quality`

### 说明

- **浏览器内 JA3 实改**依赖定制 Chromium；v6 绑定 TLS 人格 + 出站 mihomo uTLS/`client-fingerprint`，并在 stealth 中记录 JA3/JA4 label 供一致性与审计。
- 启动注入：`engines/chromium.py` / `camoufox_engine.py` → `stealth_svc.apply_stealth_to_context`。


## v7 ✅（2026-07-28）

| # | 项 | 状态 | 验证 |
|---|---|---|---|
| 1 | RPA 工作流（写步骤/定时） | ✅ | `rpa-save/list/run/schedule`；`/api/rpa/*`；dry-run OK |
| 2 | 批量创建 + 国家漂移 | ✅ | `batch-create -c JP -n 2` → 2 profiles + viewport/city jitter |
| 3 | 内置 2FA/TOTP | ✅ | `totp-add/list/code`（id 或 name）；纯 stdlib HMAC |
| 4 | 一键网络诊断 | ✅ | `diagnose`：proxy/DNS/WebRTC/IP geo/quality 报告 → `logs/diagnose/` |
| 5 | 虚拟摄像头/麦克风 | ✅ | `virtual-media --enable`；`meta.enable_virtual_media` |
| 6 | Profile 完整迁移 | ✅ | `migrate-export/import` → 新 id + 端口重分配 |
| 7 | 全球国家模板 | ✅ | `env_packs_global` 合并后 **112** packs |

### 实测摘要

- `create_app` / health → **1.7.0-v7**
- 国家模板 API `/api/templates/packs` → 112
- batch `v7jp-01/02` 创建成功，group=`batch-JP`
- TOTP `demo` secret `JBSWY3DPEHPK3PXP` 可按 name 取码
- RPA `demo-check` dry-run OK
- migrate zip `data/exports/migrate/migrate_v7jp-01-*` → 导入 `v7jp-migrated-*`
- doctor overall **PASS**
- Web `http://127.0.0.1:17888` 导航「v7 工具箱」

### 说明

- RPA 当前为 **JSON 步骤编写 + 调度**；交互式“录制器”可后续补（步骤模型已支持 goto/click/fill/scroll/wait/screenshot/js/totp）
- diagnose 在 mihomo 未启动时 proxy/ip_geo 会 fail（预期）；DNS/WebRTC 策略仍可本地判定
- 虚拟媒体默认关闭，启动时由 chromium init script 注入

### 命令

```bash
cd /home/baoge/Mozilla && source .venv/bin/activate
export PYTHONPATH=$PWD/app PLAYWRIGHT_BROWSERS_PATH=$PWD/runtime/browsers XDG_CACHE_HOME=$PWD/runtime/cache

python -m mozilla_manager.cli countries
python -m mozilla_manager.cli batch-create -c JP -n 3 --prefix shop
python -m mozilla_manager.cli totp-add --name github --secret JBSWY3DPEHPK3PXP
python -m mozilla_manager.cli totp-code github
python -m mozilla_manager.cli rpa-save --name check --profile <id> --steps '[{"action":"goto","url":"https://example.com"},{"action":"screenshot","name":"t.png"}]'
python -m mozilla_manager.cli rpa-run check --profile <id> --dry-run
python -m mozilla_manager.cli rpa-schedule --id daily-check --wf check --profile <id> --daily 09:30
python -m mozilla_manager.cli diagnose <id> --samples 4
python -m mozilla_manager.cli migrate-export <id>
python -m mozilla_manager.cli migrate-import --path data/exports/migrate/xxx.zip --name moved
python -m mozilla_manager.cli virtual-media <id> --enable
python -m mozilla_manager.cli doctor
python -m mozilla_manager.cli serve
```

### API

- `POST /api/batch/create`
- `GET|POST /api/rpa/workflows` · `POST /api/rpa/workflows/{id}/run` · schedules/scheduler
- `GET|POST /api/totp/accounts` · `.../code` · `.../fill`
- `POST /api/diagnose/profiles/{id}`
- `POST /api/transfer/profiles/{id}/export` · `POST /api/transfer/import`
- `POST /api/media/profiles/{id}`

## v8 ✅（2026-07-28）

| # | 项 | 状态 | 验证 |
|---|---|---|---|
| 1 | RPA 交互录制器 | ✅ | `record-start/poll/stop`；`/api/recorder/*`；运行中 Chromium 注入钩子 |
| 2 | 环境行内快捷 | ✅ | 诊断/迁移/复制/标签/录制 按钮 |
| 3 | 标签系统 | ✅ | `tag-add/list/remove`；筛选器 filterTag |
| 4 | 任务中心 | ✅ | `data/jobs` + stale reap；Web 异步 bulk-diagnose |
| 5 | 批量诊断 | ✅ | CLI 默认同步；API 可 async |
| 6 | 仪表盘 / 历史 | ✅ | `/api/ops/dashboard|history`；顶栏 dashStrip |
| 7 | 新建国家 112 | ✅ | create_modal 拉 `/api/templates/packs` |

### 命令

```bash
python -m mozilla_manager.cli tag-add <id> --tags 'shop,JP'
python -m mozilla_manager.cli dashboard
python -m mozilla_manager.cli bulk-diagnose --ids <id1,id2>
python -m mozilla_manager.cli record-start <running_id>
python -m mozilla_manager.cli record-stop <id> --name myflow
python -m mozilla_manager.cli jobs
python -m mozilla_manager.cli history
```

### API

- `/api/recorder/profiles/{id}/start|poll|stop`
- `/api/tags` `/api/tags/profiles/{id}/add`
- `/api/jobs` `/api/ops/dashboard|history|bulk-diagnose`

## v9 ✅（2026-07-28）

| # | 项 | 状态 | 验证 |
|---|---|---|---|
| 1 | 通知中心 | ✅ | `notify-push/list`；`/api/notify`；侧栏未读徽章 |
| 2 | 环境锁 | ✅ | lock 后 launch/delete 拦截；行内锁定按钮 |
| 3 | Watchdog 巡检调度 | ✅ | login_check / diagnose(+auto failover) / net_quality |
| 4 | 任务进度 | ✅ | `jobs.progress` pct + bulk-diagnose 步进 |
| 5 | 录制时间线 | ✅ | `record-timeline` / `/api/recorder/.../timeline` |
| 6 | 审计流 | ✅ | `audit` / `/api/audit` |
| 7 | 仪表盘增强 | ✅ | notices_unread / locked / watchdogs |

### 命令

```bash
python -m mozilla_manager.cli notify-list
python -m mozilla_manager.cli lock <id> --reason maintain
python -m mozilla_manager.cli unlock <id>
python -m mozilla_manager.cli watchdog-add <id> --kind diagnose --every 60 --auto-failover
python -m mozilla_manager.cli watchdog-tick
python -m mozilla_manager.cli audit --limit 20
python -m mozilla_manager.cli record-timeline <id>
```

## v10 ✅（2026-07-28）

| # | 项 | 状态 | 验证 |
|---|---|---|---|
| 1 | 机器身份 | ✅ | `machine` / `data/fleet/machine.json` |
| 2 | Fleet 多机同步包 | ✅ | export meta zip · import merge watchdogs/rpa/nodes |
| 3 | 本地密钥保险库 | ✅ | vault-put/get --reveal · PBKDF2+HMAC |
| 4 | 运维报表 JSON/HTML | ✅ | `report-ops` → data/reports/ |
| 5 | 整机数据备份 | ✅ | `backup` 397 files · schedule 可配 |
| 6 | 任务进度 WebSocket | ✅ | `/ws/jobs` `/ws/jobs/{id}` |
| 7 | UI 工具箱 v10 | ✅ | Fleet/报表/备份/保险库/WS 状态 |

### 命令

```bash
python -m mozilla_manager.cli machine --name my-pc
python -m mozilla_manager.cli fleet-export --name meta
python -m mozilla_manager.cli fleet-export --ids <id> --name with-data
python -m mozilla_manager.cli fleet-import --path data/fleet/outbox/meta.zip
python -m mozilla_manager.cli vault-put api --value 'xxx'
python -m mozilla_manager.cli report-ops
python -m mozilla_manager.cli backup --label daily
python -m mozilla_manager.cli backup-schedule --every 24 --enable
```

### 多机流程

1. A: `fleet-export` → `data/fleet/outbox/*.zip`
2. 拷到 B: `data/fleet/inbox/`
3. B: `fleet-import --path ...`
4. 需要完整环境时 A 用 `--ids` / `--all-data` 打入 migrate zip

## 桌面客户端 ✅（跨平台程序入口）

- `python -m mozilla_manager.client` / `cli client` / `scripts/run_client.sh|.bat`
- 模块：`client/{app,runtime,window_webview,window_tk,bridge,config}`
- Web 管理台与 API 仍按功能拆分；客户端只做「程序壳 + 托管后端」
- 配置：`data/client/client.json`

## Launch 自动重绑 ✅
- 默认 `meta.auto_rebind_on_launch=true`（缺省亦视为开启）
- 每次 `launch`：mihomo/socks5 就绪后探测出口 IP → 重绑 **timezone_id / locale / geolocation**
- 同国：保留 UA/viewport/fingerprint；换国：套用国家模板再覆盖真实 tz/geo
- 关闭：`python -m mozilla_manager.cli auto-rebind <id> --disable`
- 立即重绑：`rebind-now <id>` / `POST /api/health/profiles/{id}/rebind-env`
