# Camoufox 下载（镜像 + 断点续传）

官方 GitHub Release 在国内常年 ~200KB/s，492MB 要半小时+，还容易中断。

## 推荐方式

**Windows 桌面目录：**
```
C:\Users\zhang\Desktop\Mozilla\install_camoufox.bat
# 或
安装Camoufox.bat
```

**Ubuntu 开发根：**
```bash
cd /home/baoge/Mozilla
python scripts/fetch_camoufox.py
# 或指定官方 URL（仍会走镜像列表）:
python scripts/fetch_camoufox.py --url 'https://github.com/daijro/camoufox/releases/download/v152.0.4-beta.28/camoufox-152.0.4-beta.28-win.x86_64.zip'
```

## 能力

1. 多镜像自动切换（ghfast / ghproxy / mirror.ghproxy / gitclone / moeyy 等）
2. `tmp/*.part` **断点续传**（失败重跑接着下）
3. 装到 `runtime/cache/camoufox`（ROOT 内）
4. 支持本地 zip：`--zip tmp/xxx.zip`
5. 一键总装 `install_all_deps` 已改为调用本脚本，不再裸跑 `camoufox fetch`

## 手动浏览器下载后安装

若用 IDM/aria2 下好 zip，放到项目 `tmp\` 后：

```bat
.venv\Scripts\python.exe scripts\fetch_camoufox.py --zip tmp\camoufox-152.0.4-beta.28-win.x86_64.zip
```

## 版本

默认固定：`152.0.4-beta.28`（win/lin/mac 自动选资产名）
