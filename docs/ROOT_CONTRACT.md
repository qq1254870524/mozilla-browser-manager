# 目录契约（强制）

## 双目录模型

| 角色 | 路径 | 允许做什么 |
|------|------|------------|
| **唯一开发根（源码真相）** | `/home/baoge/Mozilla`<br>`\\wsl.localhost\Ubuntu\home\baoge\Mozilla` | 改代码、修 bug、跑 Ubuntu 测试、写日志/tmp/**仅此树内** |
| **Windows 实测副本** | `C:\Users\zhang\Desktop\Mozilla`<br>`/mnt/c/Users/zhang/Desktop/Mozilla` | **只运行/测试**；由导出脚本从开发根复制过来 |

## 硬规则

1. **开发只能在** `/home/baoge/Mozilla`。禁止在 Ubuntu 其他目录产生本项目源码、venv、profile、日志、缓存、临时文件。
2. **Windows 使用目录固定为** `C:\Users\zhang\Desktop\Mozilla`。不要在别的盘符/文件夹散落第二份“开发树”。
3. 流程永远是：
   ```
   在 /home/baoge/Mozilla 修复
     → bash scripts/export_to_windows.sh
     → 在 C:\Users\zhang\Desktop\Mozilla 实测
     → 问题回到 /home/baoge/Mozilla 再修
   ```
4. 程序运行时的 `ROOT` = 当前这棵目录树（`paths.py` 由文件位置推导）：
   - Ubuntu 开发时 ROOT=`/home/baoge/Mozilla`
   - Windows 实测时 ROOT=`C:\Users\zhang\Desktop\Mozilla`
   - 全部写入经 `safe_resolve()` 锁在**当前 ROOT 内**，不写到 Desktop 以外、不写到 `/tmp` 系统目录、不写到用户主目录散落文件。

## 实现

- `app/mozilla_manager/paths.py` → `ROOT` + `safe_resolve()` + `ensure_layout()`
- `PLAYWRIGHT_BROWSERS_PATH=$ROOT/runtime/browsers`
- mihomo / patches / exports / logs / tmp / data 全部在 `$ROOT/...`
- 同步：`scripts/export_to_windows.sh`（默认目标桌面 Mozilla）

## 导出注意

- 默认**不复制** Linux `.venv` / `runtime/browsers`（Windows 用不了 Linux 二进制）
- Windows 端用 `install_windows_deps.bat` 重建 venv 与浏览器
- 源码与 `app/`、`scripts/`、bat 启动停止脚本必须从开发根导出
