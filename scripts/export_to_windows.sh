#!/usr/bin/env bash
# 从唯一开发根 /home/baoge/Mozilla 导出到 Windows 实测目录
# DEV  : /home/baoge/Mozilla   (只在这里改代码)
# RUN  : C:\Users\zhang\Desktop\Mozilla  (只在这里测软件)
# 禁止在其他 Ubuntu 目录产生本项目文件。
# 用法:
#   bash scripts/export_to_windows.sh
#   bash scripts/export_to_windows.sh "/mnt/c/Users/zhang/Desktop/Mozilla"
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DST="${1:-/mnt/c/Users/zhang/Desktop/Mozilla}"


# Guard: must run from canonical dev root
if [[ "$ROOT" != "/home/baoge/Mozilla" ]]; then
  echo "[export][ERROR] 开发根必须是 /home/baoge/Mozilla，当前 ROOT=$ROOT" >&2
  echo "[export][ERROR] 禁止在其他目录维护/导出本项目。" >&2
  exit 1
fi
echo "[export] SRC=$ROOT"
echo "[export] DST=$DST"
mkdir -p "$DST"

# 完整代码与数据；排除仅 Linux 的 venv/缓存/大体积浏览器（Windows 端用 bat 重装）
# 如需连 runtime/browsers 一起拷，加环境变量 COPY_BROWSERS=1
RSYNC_EXCLUDES=(
  --exclude '.venv/'
  --exclude 'logs/'
  --exclude 'tmp/'
  --exclude '__pycache__/'
  --exclude '*.pyc'
  --exclude '.pytest_cache/'
  --exclude 'runtime/cache/'
  --exclude 'runtime/xdg-config/'
  --exclude 'runtime/xdg-data/'
  --exclude 'camoufox-*-lin*'
)
if [[ "${COPY_BROWSERS:-0}" != "1" ]]; then
  RSYNC_EXCLUDES+=(--exclude 'runtime/browsers/')
fi

rsync -a "${RSYNC_EXCLUDES[@]}" "$ROOT/" "$DST/"

# 根目录一键脚本必须在
for f in \
  "下载依赖.bat" "启动客户端.bat" "启动WEB.bat" "停止WEB.bat" \
  "Windows使用说明.txt" "scripts/win_actions.py" "scripts/install_all_deps.py" "scripts/fetch_camoufox.py"
do
  if [[ ! -f "$DST/$f" ]]; then
    echo "[export][warn] missing $f — check repo root"
  else
    echo "[export] ok $f"
  fi
done

# 清单
{
  echo "exported_at=$(date -Iseconds)"
  echo "src=$ROOT"
  echo "dst=$DST"
  find "$DST" -maxdepth 2 -type f \( -name '*.bat' -o -name '*.txt' -o -name 'requirements.txt' -o -name 'pyproject.toml' \) | sort
} > "$DST/EXPORT_MANIFEST.txt"

echo "[export] done"
echo "[export] 在 Windows 资源管理器打开: $DST"
echo "[export] 首次双击: 下载依赖.bat  然后  启动客户端.bat"
