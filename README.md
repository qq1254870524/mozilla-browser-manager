# Mozilla Browser Manager

便携多引擎浏览器管理器 · **Windows + Ubuntu/WSL**  
**开发根（唯一）：** `/home/baoge/Mozilla`（`\\wsl.localhost\Ubuntu\home\baoge\Mozilla`）  
**Windows 四按钮（仅）：** `下载依赖` / `启动客户端` / `启动WEB` / `停止WEB`  
**Windows 实测：** `C:\\Users\\zhang\\Desktop\\Mozilla`（由 `scripts/export_to_windows.sh` 导出，不在此主开发）

## 产品形态进度

见 [docs/ROADMAP_STATUS.md](docs/ROADMAP_STATUS.md)

- MVP CLI ✅
- 本地 Web 管理台（AdsPower 风格）✅ → `http://127.0.0.1:17888`
- **v2** 节点国家推荐 / 指纹模板 / 仅浏览器代理 / 会话备份 ✅
- **v3** SQLite / 一致性 / 测速 / 扩展 ✅
- **v4** Cookie / 时间旅行 / failover / WebRTC·DoH ✅
- **v5** `runtime/nodes` 本地节点库 / 订阅切换导出 / 内置 CF Turnstile ✅
- **v6** TLS/JA3/JA4 人格 · 24+ 维指纹 · 强制 DoH · 网络质量/归属地校验 ✅
- **v7** RPA/2FA/批量建档/网络诊断/迁移/虚拟媒体/全球模板 ✅
- **v8** RPA录制 / 标签 / 任务中心 / 批量诊断 / 仪表盘 / 行内运维 ✅
- **v9** 巡检Watchdog / 通知中心 / 环境锁 / 任务进度 / 审计流 ✅
- **v10** Fleet多机同步 / 密钥库 / 运维报表 / 整机备份 / WS任务流 ✅
- **v10.1** 现有功能细节增强 / Camoufox对齐 / UI重绑·隐私·Cookie / 全量合规审计 86/86 ✅

## 内置

详情见 [docs/BUILTINS.md](docs/BUILTINS.md)。

- 内核： [Camoufox](https://github.com/daijro/camoufox) · [Playwright](https://github.com/microsoft/playwright)
- 补丁： [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) · [rebrowser-patches](https://github.com/rebrowser/rebrowser-patches)
- 代理内核： mihomo（`runtime/mihomo/`）
- CF 盾： [turnstile-harvester1](https://github.com/qq1254870524/turnstile-harvester1)（`runtime/vendors/`）

## 安装（全部进本目录）

**一键双端（按 OS 自动下载）：**

```bash
# Ubuntu/WSL 开发根
bash install_deps.sh
# Windows 实测目录（桌面 Mozilla）双击：
#   install_windows_deps.bat  /  一键安装依赖.bat
# 核心逻辑：python scripts/install_all_deps.py
```

详见 [docs/INSTALL_DEPS.md](docs/INSTALL_DEPS.md)。


```bash
cd /home/baoge/Mozilla
bash scripts/bootstrap_runtime.sh
source .venv/bin/activate
export PYTHONPATH=$PWD/app
export PLAYWRIGHT_BROWSERS_PATH=$PWD/runtime/browsers
python -m mozilla_manager.cli doctor
```

## 桌面客户端（推荐，程序启动）

跨平台 **Windows + Ubuntu**：启动的是本地程序，不是让你去开网页。

```bash
bash scripts/run_client.sh          # Ubuntu
python -m mozilla_manager.client    # 通用
python -m mozilla_manager.cli client
```

**Windows 根目录一键脚本（复制到 Windows 后双击）：**

| 文件 | 作用 |
|------|------|
| `启动客户端.bat` | 桌面客户端（**关窗 = 停掉 API/浏览器/mihomo/后台**） |
| `启动Web.bat` | 仅 Web `http://127.0.0.1:17888` |
| `一键安装Windows依赖.bat` | 首次：venv + pip + Chromium |
| `Windows使用说明.txt` | 完整说明 |
| `scripts\run_client.bat` / `run_web.bat` / `bootstrap_runtime.bat` | 英文路径备用 |

从 WSL 导出到 Windows 桌面：

```bash
bash scripts/export_to_windows.sh
# 或
bash scripts/export_to_windows.sh "/mnt/c/Users/zhang/Desktop/Mozilla"
```

- 进程内拉起模块化 API（`modules/*` + `api/routes/*`）
- 原生窗口内嵌 Web 管理台（`pywebview`；否则 Tk 控制台壳）
- 详见 [docs/CLIENT.md](docs/CLIENT.md) · [Windows使用说明.txt](Windows使用说明.txt)

## Web 管理台

```bash
cd /home/baoge/Mozilla
source .venv/bin/activate
export PYTHONPATH=$PWD/app
export PLAYWRIGHT_BROWSERS_PATH=$PWD/runtime/browsers
python -m mozilla_manager.cli serve
# 或
bash scripts/run_web.sh
```

打开：http://127.0.0.1:17888/

页面：
- 环境管理（列表 / 打开 / 停止 / 删除 / 检测）
- 分组管理
- 代理管理
- 订阅 / 节点（导入·切换·导出全部节点 · runtime/nodes）
- CF Turnstile 一键过盾（内置 harvester）
- 系统诊断 doctor
- **v10 工具箱**：批量创建 / 2FA / RPA / 诊断 / 迁移 / 虚拟媒体 / 国家模板数

## CLI 常用

```bash
python -m mozilla_manager.cli list
python -m mozilla_manager.cli create -n demo-de --country DE --auto-port --engine pw_chromium --patch patchright
python -m mozilla_manager.cli sub-import --url 'https://liangxin.xyz/api/v1/liangxin?OwO=...' --name default
python -m mozilla_manager.cli mihomo-start --port 17822 --sub default
python -m mozilla_manager.cli launch <profile_id>   # 默认按出口IP重绑 tz/locale/geo
python -m mozilla_manager.cli auto-rebind <id> --disable
python -m mozilla_manager.cli rebind-now <id>
python -m mozilla_manager.cli stop <profile_id>
python -m mozilla_manager.cli recommend-node "🇯🇵日本高速01"
python -m mozilla_manager.cli create -n demo-jp --node "🇯🇵日本高速01" --auto-port
python -m mozilla_manager.cli session-backup <id>
python -m mozilla_manager.cli sub-switch default
python -m mozilla_manager.cli sub-export --name default --fmt zip
python -m mozilla_manager.cli turnstile-vendor
python -m mozilla_manager.cli stealth-show <id>
python -m mozilla_manager.cli net-quality <id>
python -m mozilla_manager.cli batch-create -c JP -n 3 --prefix shop
python -m mozilla_manager.cli totp-add --name demo --secret JBSWY3DPEHPK3PXP
python -m mozilla_manager.cli diagnose <id>
python -m mozilla_manager.cli migrate-export <id>
python -m mozilla_manager.cli countries
python -m mozilla_manager.cli dashboard
python -m mozilla_manager.cli tag-add <id> --tags shop,JP
python -m mozilla_manager.cli bulk-diagnose --ids <id>
python -m mozilla_manager.cli record-start <running_id>
python -m mozilla_manager.cli lock <id>
python -m mozilla_manager.cli watchdog-add <id> --kind diagnose --every 60 --auto-failover
python -m mozilla_manager.cli notify-list
python -m mozilla_manager.cli fleet-export --name meta
python -m mozilla_manager.cli backup --label daily
python -m mozilla_manager.cli vault-put key --value secret
python -m mozilla_manager.cli report-ops
python -m mozilla_manager.cli compliance
python -m mozilla_manager.cli backfill-meta
```

## 模块化

业务 / API / 前端按功能拆分，见 [docs/MODULES.md](docs/MODULES.md)。
改某一块只动对应 module，避免巨石文件。

## 目录契约

禁止在其他目录产生本项目文件。全部路径经 `paths.safe_resolve` 锁在 ROOT 下。
