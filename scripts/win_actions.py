#!/usr/bin/env python3
"""Windows 四入口统一实现：启动客户端 / 启动WEB / 停止WEB / 下载依赖。

只由根目录 4 个中文 .bat 调用。逻辑全在这里，避免一堆重复 bat。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def _pause() -> None:
    if os.name == "nt":
        try:
            input("\n按回车键关闭窗口...")
        except EOFError:
            time.sleep(2)


def die(msg: str, code: int = 1) -> None:
    print(f"[错误] {msg}")
    _pause()
    raise SystemExit(code)


def ensure_root() -> None:
    if not (ROOT / "app" / "mozilla_manager").is_dir():
        die(f"不是项目目录: {ROOT}")
    s = str(ROOT).replace("/", "\\").lower()
    if "wsl.localhost" in s or s.startswith("\\\\"):
        die(
            "不要从 \\\\wsl.localhost\\... 运行！\n"
            "请打开本地目录: C:\\Users\\zhang\\Desktop\\Mozilla"
        )
    if "\\windows\\system32" in s or "\\windows\\syswow64" in s:
        die(f"拒绝在系统目录运行: {ROOT}")
    os.chdir(ROOT)
    # env locked to ROOT
    os.environ["PYTHONPATH"] = str(ROOT / "app")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(ROOT / "runtime" / "browsers")
    os.environ["XDG_CACHE_HOME"] = str(ROOT / "runtime" / "cache")
    os.environ["XDG_CONFIG_HOME"] = str(ROOT / "runtime" / "xdg-config")
    os.environ["XDG_DATA_HOME"] = str(ROOT / "runtime" / "xdg-data")
    os.environ["MOZILLA_MANAGER_ROOT"] = str(ROOT)


def venv_python() -> Path:
    if os.name == "nt":
        return ROOT / ".venv" / "Scripts" / "python.exe"
    return ROOT / ".venv" / "bin" / "python"


def have_venv() -> bool:
    return venv_python().is_file()


def create_venv() -> None:
    print("[1/2] 创建虚拟环境 .venv ...")
    candidates = []
    if os.name == "nt":
        candidates = [
            ["py", "-3.12", "-m", "venv", str(ROOT / ".venv")],
            ["py", "-3.11", "-m", "venv", str(ROOT / ".venv")],
            ["py", "-3", "-m", "venv", str(ROOT / ".venv")],
            [sys.executable, "-m", "venv", str(ROOT / ".venv")],
        ]
    else:
        candidates = [[sys.executable, "-m", "venv", str(ROOT / ".venv")]]
    ok = False
    for cmd in candidates:
        print("  $", " ".join(cmd))
        r = subprocess.run(cmd, cwd=str(ROOT))
        if r.returncode == 0 and have_venv():
            ok = True
            break
    if not ok:
        die("创建虚拟环境失败。请先安装 Python 3.11+，并勾选 Add python.exe to PATH。\n下载: https://www.python.org/downloads/")


def run_py(args: list[str], *, check: bool = True) -> int:
    py = str(venv_python())
    cmd = [py, *args]
    print("  $", " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(ROOT), env=os.environ.copy())
    if check and r.returncode != 0:
        die(f"命令失败，退出码 {r.returncode}")
    return r.returncode


def action_install() -> None:
    print("=" * 50)
    print("  下载依赖（自动识别系统）")
    print(f"  目录: {ROOT}")
    print("=" * 50)
    print("将安装：")
    print("  · Python 依赖（requirements.txt）")
    print("  · 补丁栈：patchright + rebrowser-playwright + 源码")
    print("  · Chromium 浏览器内核（镜像+断点续传）")
    print("  · Camoufox（镜像+断点续传）")
    print("  · mihomo 代理核心（镜像+断点续传）")
    print("  · 中断后重新点「下载依赖」会自动续传")
    print("  · 全部只下载到本文件夹内")
    print()
    if not have_venv():
        create_venv()
    else:
        print("[跳过] 虚拟环境已存在")
    print()
    print("[2/2] 安装全部依赖（按当前系统自动选择 Windows/Linux 包）...")
    code = run_py([str(ROOT / "scripts" / "install_all_deps.py")], check=False)
    # Camoufox explicit (mirrors) in case optional path skipped/failed
    print()
    print("[补充] Chromium（镜像加速 + 断点续传）...")
    run_py([str(ROOT / "scripts" / "fetch_chromium.py")], check=False)
    print("[补充] Camoufox（镜像加速 + 断点续传）...")
    run_py([str(ROOT / "scripts" / "fetch_camoufox.py")], check=False)
    print("[补充] mihomo（镜像加速 + 断点续传）...")
    run_py([str(ROOT / "scripts" / "install_all_deps.py"), "--force-mihomo", "--skip-optional", "--skip-doctor"], check=False)
    print("[补充] 补丁栈挂接（rebrowser / patchright）...")
    run_py(
        [
            "-c",
            "import importlib.util; from pathlib import Path; "
            "p=Path('scripts')/'install_all_deps.py'; "
            "s=importlib.util.spec_from_file_location('iad', p); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            "m.ensure_rebrowser_stack()",
        ],
        check=False,
    )
    if code != 0:
        print("[警告] 主安装过程有错误，请向上滚动查看。可再运行一次「下载依赖」。")
    else:
        print()
        print("[完成] 依赖已就绪。接下来可双击：启动客户端  或  启动WEB")
    _pause()


def _ensure_ready_or_install() -> None:
    if have_venv():
        return
    print("[提示] 还没有安装依赖，正在自动执行「下载依赖」...")
    print()
    # inline install without final pause twice - temporarily
    if not have_venv():
        create_venv()
    run_py([str(ROOT / "scripts" / "install_all_deps.py")], check=False)
    run_py([str(ROOT / "scripts" / "fetch_camoufox.py")], check=False)
    if not have_venv():
        die("依赖安装失败，请先双击「下载依赖」。")


def action_start_client() -> None:
    print("=" * 50)
    print("  启动客户端")
    print(f"  目录: {ROOT}")
    print("=" * 50)
    _ensure_ready_or_install()
    print()
    print("正在启动桌面客户端...")
    print("说明：关闭客户端窗口 = 停止全部服务")
    print()
    code = run_py(["-m", "mozilla_manager.client"], check=False)
    print()
    print(f"[结束] 退出码 {code}")
    _pause()
    raise SystemExit(code)


def action_start_web() -> None:
    print("=" * 50)
    print("  启动 WEB 管理台")
    print("  地址: http://127.0.0.1:17888")
    print(f"  目录: {ROOT}")
    print("=" * 50)
    _ensure_ready_or_install()
    print()
    print("正在启动 WEB...")
    print("停止方式：再双击「停止WEB」，或关闭本窗口")
    print()
    code = run_py(["-m", "mozilla_manager.web"], check=False)
    print()
    print(f"[结束] 退出码 {code}")
    _pause()
    raise SystemExit(code)


def _taskkill_pids(pids: set[int]) -> None:
    for pid in sorted(pids):
        if pid <= 0:
            continue
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"  已结束进程 PID={pid}")


def action_stop_web() -> None:
    print("=" * 50)
    print("  停止 WEB / 相关服务")
    print(f"  目录: {ROOT}")
    print("=" * 50)

    # 1) graceful if venv present
    if have_venv():
        print("[1] 尝试优雅停止浏览器/mihomo/后台任务...")
        run_py(
            [
                "-c",
                "from mozilla_manager.modules.system import shutdown_all; "
                "import json; print(json.dumps(shutdown_all(stop_browsers=True, stop_mihomo=True), ensure_ascii=False, indent=2))",
            ],
            check=False,
        )
    else:
        print("[1] 无虚拟环境，跳过优雅停止")

    # 2) pid files
    print("[2] 清理 pid 文件...")
    for rel in ("runtime/mozilla-web.pid", "logs/web.pid"):
        pf = ROOT / rel
        if pf.is_file():
            try:
                pid = int(pf.read_text(encoding="utf-8").strip().split()[0])
                _taskkill_pids({pid})
            except Exception:
                pass
            try:
                pf.unlink()
            except OSError:
                pass

    # 3) PowerShell sweep
    print("[3] 强制结束本项目相关进程（WEB/客户端/mihomo）...")
    if os.name == "nt":
        ps = r"""
$ErrorActionPreference='SilentlyContinue'
$root = (Resolve-Path -LiteralPath '.').Path
$killed = @()
try {
  Get-NetTCPConnection -LocalPort 17888 -State Listen | ForEach-Object {
    $killed += $_.OwningProcess
    Stop-Process -Id $_.OwningProcess -Force
  }
} catch {}
Get-CimInstance Win32_Process | Where-Object {
  if (-not $_.CommandLine) { return $false }
  $cl = $_.CommandLine
  if ($cl -match 'mozilla_manager\.(web|client|cli)') { return $true }
  if ($cl -match 'uvicorn' -and $cl -match 'mozilla_manager') { return $true }
  if ($_.Name -match 'mihomo' -and ($cl -like ('*'+$root+'*') -or $cl -match 'runtime[\\/]mihomo|Mozilla')) { return $true }
  return $false
} | ForEach-Object {
  $killed += $_.ProcessId
  Stop-Process -Id $_.ProcessId -Force
}
$u = $killed | Select-Object -Unique
if ($u) { $u | ForEach-Object { Write-Output ("KILLED " + $_) } } else { Write-Output "NONE" }
"""
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        out = (r.stdout or "").strip()
        if out:
            for line in out.splitlines():
                print(" ", line)
        # netstat fallback
        try:
            ns = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            pids = set()
            for line in (ns.stdout or "").splitlines():
                if ":17888" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        try:
                            pids.add(int(parts[-1]))
                        except ValueError:
                            pass
            _taskkill_pids(pids)
        except Exception as e:
            print("  netstat 回退失败:", e)
    else:
        # linux fallback used rarely from this entry
        subprocess.run(["bash", str(ROOT / "stop.sh")], check=False)

    print()
    print("[完成] 已停止 WEB 及相关服务。")
    _pause()


def main(argv: list[str] | None = None) -> int:
    _setup_stdio()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("用法: win_actions.py [下载依赖|启动客户端|启动WEB|停止WEB]")
        print("  install | client | web | stop")
        return 1
    raw = argv[0].strip().lower()
    mapping = {
        "install": "install",
        "deps": "install",
        "下载依赖": "install",
        "client": "client",
        "start-client": "client",
        "启动客户端": "client",
        "web": "web",
        "start-web": "web",
        "启动web": "web",
        "stop": "stop",
        "stop-web": "stop",
        "停止web": "stop",
        "停止": "stop",
    }
    # normalize fullwidth etc
    key = mapping.get(raw) or mapping.get(raw.replace(" ", ""))
    if key is None:
        # try contains
        if "依赖" in raw or "install" in raw:
            key = "install"
        elif "客户端" in raw or "client" in raw:
            key = "client"
        elif "停止" in raw or "stop" in raw:
            key = "stop"
        elif "web" in raw or "WEB" in argv[0] or "管理" in raw:
            key = "web"
    if key is None:
        die(f"未知命令: {argv[0]}")

    ensure_root()
    print(f"项目目录: {ROOT}")
    print()

    if key == "install":
        action_install()
    elif key == "client":
        action_start_client()
    elif key == "web":
        action_start_web()
    elif key == "stop":
        action_stop_web()
    else:
        die(f"未实现: {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
