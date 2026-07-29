# 一键安装依赖（双端自动识别）

## 原则

- **开发根** `/home/baoge/Mozilla`：Ubuntu/WSL 安装 **Linux** 依赖
- **实测副本** `C:\Users\zhang\Desktop\Mozilla`：安装 **Windows** 依赖
- 同一套 `requirements.txt`（Python 包双端共用）
- 浏览器内核 / mihomo **按当前操作系统自动下载对应平台二进制**
- 全部写入当前 `ROOT` 内，不写到其他目录

## 入口

| 系统 | 命令 |
|------|------|
| Ubuntu/WSL | `bash install_deps.sh` 或 `bash 一键安装依赖.sh` 或 `bash scripts/bootstrap_runtime.sh` |
| Windows 桌面 | 双击 `install_windows_deps.bat` / `一键安装依赖.bat` / `一键安装Windows依赖.bat` |
| 通用 | `python scripts/install_all_deps.py`（需已有/可建 venv） |

## 安装内容

1. `.venv` + `pip install -r requirements.txt`
2. Playwright Chromium → `runtime/browsers`
3. Patchright Chromium
4. Camoufox + geoip（可选可 `--skip-optional`）
5. rebrowser-playwright chromium
6. mihomo：
   - Linux → `runtime/mihomo/mihomo`
   - Windows → `runtime/mihomo/mihomo.exe`
7. `python -m mozilla_manager.cli doctor`

## 参数

```bash
python scripts/install_all_deps.py --skip-optional   # 跳过 camoufox/rebrowser/patches
python scripts/install_all_deps.py --force-mihomo    # 强制重下 mihomo
python scripts/install_all_deps.py --skip-doctor
```

## 流程

```
WSL:  bash install_deps.sh
WSL:  bash scripts/export_to_windows.sh
Win:  双击 install_windows_deps.bat   # 自动装 Windows 版内核
Win:  双击 start_client.bat
```
