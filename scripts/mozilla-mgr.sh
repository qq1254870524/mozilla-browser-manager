# =============================================
# 最终修复版启动脚本（已适配当前目录结构）
# =============================================
# 文件位置: /home/baoge/Mozilla/scripts/mozilla-mgr.sh

#!/bin/bash
# Mozilla Browser Manager 一键启动脚本（最终修复版）

cd /home/baoge/Mozilla

# ==================== 核心环境变量 ====================
export PYTHONPATH=$PWD/app
export PLAYWRIGHT_BROWSERS_PATH=$PWD/runtime/browsers
export XDG_CACHE_HOME=$PWD/runtime/cache
export ROOT=$PWD

# ==================== 日志 ====================
LOG_FILE="$ROOT/logs/mozilla-mgr-$(date +%Y%m%d-%H%M).log"
echo "=== Mozilla Browser Manager v10.2 启动 ===" | tee -a "$LOG_FILE"
date '+%Y-%m-%d %H:%M:%S' | tee -a "$LOG_FILE"

# ==================== 启动方式 ====================
MODE="web"

while [[ $# -gt 0 ]]; do
    case $1 in
        --client | -c) MODE="client" ;;
        --web | -w) MODE="web" ;;
        *) echo "未知参数: $1" ;;
    esac
    shift
done

if [ "$MODE" = "client" ]; then
    echo "启动桌面客户端..." | tee -a "$LOG_FILE"
    python -m mozilla_manager.client
else
    echo "启动 Web 管理台..." | tee -a "$LOG_FILE"
    uvicorn mozilla_manager.web:app --host 0.0.0.0 --port 17888 --log-level info
fi

echo "=== 启动完成 ===" | tee -a "$LOG_FILE"