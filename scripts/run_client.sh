# =============================================
# 桌面客户端一键启动脚本（Ubuntu 版）—— v10.1.1 健壮版
# =============================================
# 文件位置: /home/baoge/Mozilla/scripts/run_client.sh

#!/bin/bash
# Mozilla Browser Manager 桌面客户端一键启动脚本
# v10.1.1 — 完全健壮版（2026-07-29）

cd /home/baoge/Mozilla

# ==================== 核心环境变量 ====================
export PYTHONPATH=$PWD/app
export PLAYWRIGHT_BROWSERS_PATH=$PWD/runtime/browsers
export XDG_CACHE_HOME=$PWD/runtime/cache
export ROOT=$PWD

# ==================== 日志记录 ====================
LOG_FILE="$ROOT/logs/client-start-$(date +%Y%m%d-%H%M).log"
echo "=== Mozilla Browser Manager 桌面客户端启动 ===" | tee -a "$LOG_FILE"
date '+%Y-%m-%d %H:%M:%S' | tee -a "$LOG_FILE"

# ==================== 启动参数解析 ====================
HEADLESS=false
DEBUG=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --headless | -H) HEADLESS=true ;;
        --debug | -d) DEBUG=true ;;
        *) echo "未知参数: $1" ;;
    esac
    shift
done

if $DEBUG; then
    export DEBUG=1
    echo "DEBUG 模式已开启" | tee -a "$LOG_FILE"
fi

# ==================== 启动客户端 ====================
echo "正在启动桌面客户端..." | tee -a "$LOG_FILE"

if $HEADLESS; then
    echo "HEADLESS 模式启动（无界面）" | tee -a "$LOG_FILE"
    python -m mozilla_manager.client --headless
else
    python -m mozilla_manager.client
fi

echo "=== 客户端启动完成 ===" | tee -a "$LOG_FILE"