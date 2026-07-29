# 开发 / 实测工作流（固定）

```
\\wsl.localhost\Ubuntu\home\baoge\Mozilla     ← 只在这里开发、修问题
                 │
                 │  bash scripts/export_to_windows.sh
                 ▼
C:\Users\zhang\Desktop\Mozilla                ← 只在这里运行、测软件
```

## 路径

| 环境 | 路径 | 职责 |
|------|------|------|
| Ubuntu / WSL **开发** | `/home/baoge/Mozilla` | 唯一可写开发目录 |
| Windows **使用** | `C:\Users\zhang\Desktop\Mozilla` | 实测运行目录 |

## 日常步骤

1. 在 WSL 打开开发根：
   ```bash
   cd /home/baoge/Mozilla
   ```
2. 改代码 / 修 bug / Ubuntu 侧自测（文件不得写到本树外）
3. 导出到 Windows 桌面：
   ```bash
   bash scripts/export_to_windows.sh
   # 等价于：
   # bash scripts/export_to_windows.sh "/mnt/c/Users/zhang/Desktop/Mozilla"
   ```
4. 在 Windows 桌面 `Mozilla` 里：
   - 首次：`install_windows_deps.bat`
   - 运行：`start_client.bat` 或 `start_web.bat`
   - 停止：`stop_web.bat` / `stop_all.bat`（客户端关窗即全停）
5. 实测发现问题 → **回到步骤 1 在开发根修** → 再导出覆盖桌面副本

## 禁止

- 在 `/home/baoge/xxx` 其他目录建第二份 Mozilla 开发树
- 直接在 `C:\Users\zhang\Desktop\Mozilla` 里改源码当主开发（易和 WSL 分叉）；主修仍在 WSL 开发根
- 把 Linux `.venv` 拷到 Windows 当解释器

## 一键同步

```bash
cd /home/baoge/Mozilla && bash scripts/export_to_windows.sh
```
