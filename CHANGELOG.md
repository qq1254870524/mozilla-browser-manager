# Changelog

本项目版本号：`app/mozilla_manager` 的 `__version__` / API `version` / 客户端 `client.__version__`。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [1.10.6] - 2026-07-30 — v10.6 freetaxusa「点 Create account 后全标签断网」

### 实测

- 管理器完整 launch 路径实测：`api.ip.sb` → `auth.freetaxusa.com` → 点击 **Create new account** → 新标签再取 IP → `example.com`
- **全程 mihomo mixed-port 存活**，浏览器侧 0 次 `ERR_PROXY_CONNECTION_FAILED`
- 标题可达：`FreeTaxUSA® - New Account Setup`；其他标签仍返回出口 IP

### 根因与修复

- **mihomo 进程与父进程同组**：Linux 未 `start_new_session`，父 shell/SIGHUP/客户端退出会误杀代理 → 全标签 `ERR_PROXY_CONNECTION_FAILED`
  - Linux：`start_new_session=True`
  - Windows：`CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW`
- **意外退出监视**：`mihomo-death-audit.log` + 若仍有 live 浏览器占用该 port 则自动 `start` 拉起
- **stop 审计区分**：`_INTENTIONAL_STOPS` 避免把主动 stop 当成崩溃
- **订阅回退**：`sub=default` 且无节点时回退到 **active 订阅**（及任意有节点的 sub），避免空配置/半残核心
- **Chromium 双写 `--proxy-server=`**：Playwright `proxy=` + 启动参数，降低 Network Service 重绑后丢代理
- **启动冒烟**：launch 同线程检测 mixed-port；`no-cors fetch` 软失败不拦启动；仅 port 宕机硬失败
- **keepalive** 周期 3s → **1.5s**

### 版本

- `1.10.6-v10.6` / API `1.10.6` / client `1.10.6-client`

---

## [1.10.4] - 2026-07-30 — v10.4 网络稳定性（开网页后断网）

### 严重修复

- **开网页后又断网（换节点仍复现）**
  - 运行时 watchdog 误判浏览器已死时，**不再立刻杀掉 mihomo**（此前会在窗口仍开着时切断代理）。
  - 进程存活检测改为保守策略：启动宽限期 + 连续多次 miss 才收尸；Windows 使用 `OpenProcess` 判断 PID。
  - Playwright **跨线程调用**修复：
    - 标签页自动保存 `snapshot_http_tabs` 必须经 `call_in_profile_thread`
    - CF 延迟复检禁止在 `threading.Timer` 线程直接碰 `page.*`
    - 浏览器关闭 / reconcile 收尸走 profile worker，避免 CDP 会话损坏
  - `BrowserWorker.close()`：在 worker 自身线程内不再 `join(self)`，消除死锁假死

### 网络 / 代理

- Chromium 默认 **`--disable-quic`**：HTTP3/QUIC 经 SOCKS5/mihomo 易出现「第一页正常、后续导航失败」
- mihomo 配置：
  - `enhanced-mode: redir-host`（替代易踩坑的 fake-ip 默认）
  - `tcp-concurrent: true`
  - 默认 `ipv6: false`（双栈节点抖动时更稳）
- 代理下 **不强制浏览器 DoH-only**（保留既有 anti_leak 策略，避免 DNS 引导死锁）
- SOCKS 密码含 `#` 等字符的解析继续走独立 username/password 字段

### CF 过盾

- 检测收紧：标题裸匹配 `cloudflare` **不再**当作挑战页（减少误触发卡死 worker）
- 过盾等待封顶约 20s；延迟复检仅在仍像 CF 时执行
- 默认仍 **时刻准备**（`auto_cf` / `pass_cf`），但不再拖垮整网

### 体验 / 反检测（延续 v10.3）

- 默认最强反检测：bundled Chromium + patchright + stealth_v6 + humanize，**关闭假鼠标**
- 视口默认不锁死（可自由缩放），沉浸式默认 soft，避免 Win32 扒边框导致卡顿
- 新增/完善：`engines/native_ux.py`、`engines/immersive.py`

### 版本

| 组件 | 版本 |
|------|------|
| 包 / API | `1.10.4-v10.4` / `1.10.4` |
| 桌面客户端 | `1.10.4-client` |

### 升级与重测（Windows）

开发根：`/home/baoge/Mozilla`  
实测目录：`C:\Users\zhang\Desktop\Mozilla`（`bash scripts/export_to_windows.sh`）

```text
停止WEB.bat → 关闭客户端与残留浏览器
启动客户端.bat → 启动环境 → 打开网页 → 连续点多个链接/新标签
```

若仍无网：查看 `logs/mihomo-<端口>.log`  
- 大量 `EOF` / `deadline exceeded` 且 mihomo 进程仍在 → 节点上游问题  
- 出现 `shutting down` 而窗口还开着 → 报 issue 并附日志

---

## [1.10.3] - 2026-07-30 — v10.3 沉浸式 / 有网 / 不卡 / CF

### 修复

- DoH `secure` + SOCKS/mihomo 导致整浏览器无网：代理场景跳过浏览器 DoH-only
- 窗口缩放一帧一帧：默认 `lock_viewport=false`；沉浸式改为 soft（`immersive_hard` 才强扒边框）
- CF always-ready 默认开启并回填旧配置
- 系统 Chrome 仅 comfort / 显式 `use_system_chrome`；默认捆绑 Chromium 最强反检测

---

## [1.10.1] - 2026-07-29 — v10.1 细节 + 合规

- Camoufox 对齐 cookie / 标签 / WebRTC·DoH
- UI：自动重绑、隐私、Cookie、合规核对
- 合规审计 86/86；`backfill-meta`
- 独立 user_data_dir + 每浏览器出口 + launch 按 IP 重绑

---

## [1.10.0] - 2026-07-28 — v10 Fleet

- machine_id / Fleet 同步包 / 本地密钥库
- 运维报表 / 整机备份 / WebSocket 任务进度

---

## [1.9.0] - 2026-07-28 — v9

- 通知中心 / 环境锁 / Watchdog / 任务进度 / 录制时间线 / 审计流

---

## [1.8.0] - 2026-07-28 — v8

- RPA 录制 / 标签 / 任务中心 / 批量诊断 / 仪表盘 / 全球模板

---

## 更早版本

v1–v7 功能矩阵见 [docs/ROADMAP_STATUS.md](docs/ROADMAP_STATUS.md)。
