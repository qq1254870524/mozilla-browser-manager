#!/usr/bin/env bash
# 校验跨平台便携必备文件是否齐全
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
missing=0
need=(
  "启动客户端.bat"
  "启动Web.bat"
  "一键安装Windows依赖.bat"
  "Windows使用说明.txt"
  "scripts/run_client.bat"
  "scripts/run_web.bat"
  "scripts/run_client.sh"
  "scripts/run_web.sh"
  "scripts/bootstrap_runtime.bat"
  "scripts/bootstrap_runtime.sh"
  "scripts/export_to_windows.sh"
  "requirements.txt"
  "pyproject.toml"
  "README.md"
  "app/mozilla_manager/web.py"
  "app/mozilla_manager/cli.py"
  "app/mozilla_manager/client/app.py"
  "app/mozilla_manager/ui/static/index.html"
)
echo "ROOT=$ROOT"
for f in "${need[@]}"; do
  if [[ -e "$f" ]]; then
    echo "OK  $f"
  else
    echo "MISS $f"
    missing=$((missing+1))
  fi
done
if [[ $missing -eq 0 ]]; then
  echo "ALL_PRESENT"
  exit 0
fi
echo "MISSING_COUNT=$missing"
exit 1
