# 桌面客户端打包备忘（仍锁定 ROOT 内产物）

## 开发启动

```bash
# Ubuntu / WSL
bash scripts/run_client.sh

# Windows
scripts\run_client.bat
```

## 依赖

- 必选：现有 FastAPI/uvicorn 后端
- 桌面窗体：`pywebview`（Windows 用 EdgeChromium/WebView2；Ubuntu 用 GTK/Qt）
- 无 webview 时自动降级为 **Tk 控制台壳**（仍是独立程序）

```bash
pip install -r requirements.txt
pip install 'pywebview>=5'
# Ubuntu GUI 额外系统包示例：
# sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1
```

## 打包方向（输出建议仍进 ROOT/dist）

- Windows: PyInstaller `python -m mozilla_manager.client`
- Ubuntu: PyInstaller / briefcase

模块边界不要打进单文件业务巨石：后端继续 `modules/*` + `api/routes/*`，客户端只做 runtime + window。
