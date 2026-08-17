#!/bin/bash
# service_monitor.sh
# 服务监控脚本：检查端口存活，异常时通过启停脚本自动重启
#
# 用法：crontab 定时执行，例如每分钟检查一次
#   * * * * * /path/to/monitor_process.sh

set -o pipefail

# ============ 配置区 ============
SERVICE_NAME="snc-ng-proxy-0.11.3.3.jar"
SERVICE_PORT=10031
START_SCRIPT="/home/shsnc/snc-ng-proxies/snc-ng-proxy/snc_ng_server.sh"

LOG_FILE="/var/log/service_monitor.log"
MAX_LOG_SIZE=$((10 * 1024 * 1024))   # 日志超过 10MB 自动轮转
MAX_RETRY=3                           # 重启失败后重试次数
RETRY_INTERVAL=3                      # 重试间隔（秒）
START_TIMEOUT=10                      # 启动后等待端口就绪的超时（秒）
# =================================

# ---------- 工具函数 ----------

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" >> "$LOG_FILE"
}

log_rotate() {
    if [ -f "$LOG_FILE" ] && [ "$(stat -c%s "$LOG_FILE" 2>/dev/null || stat -f%z "$LOG_FILE" 2>/dev/null || echo 0)" -ge "$MAX_LOG_SIZE" ]; then
        mv "$LOG_FILE" "${LOG_FILE}.1"
    fi
}

# 检查端口是否在监听
check_port() {
    ss -tlnp 2>/dev/null | grep -q ":${SERVICE_PORT} " && return 0
    netstat -tlnp 2>/dev/null | grep -q ":${SERVICE_PORT} " && return 0
    return 1
}

# 等待端口就绪，超时返回 1
wait_port() {
    local elapsed=0
    while [ $elapsed -lt "$START_TIMEOUT" ]; do
        check_port && return 0
        sleep 1
        elapsed=$((elapsed + 1))
    done
    return 1
}

# 调用启停脚本（同一个脚本，传入 start/stop 命令）
call_service() {
    local action="$1"
    if [ ! -f "$START_SCRIPT" ]; then
        log "[ERROR] 启停脚本不存在: $START_SCRIPT"
        return 1
    fi
    if [ ! -x "$START_SCRIPT" ]; then
        log "[WARN] 脚本无可执行权限，尝试用 bash 执行"
    fi
    bash "$START_SCRIPT" "$action" >> "$LOG_FILE" 2>&1
}

# ---------- 主逻辑 ----------

log_rotate

# 端口已监听 → 正常，直接退出
if check_port; then
    log "[INFO] $SERVICE_NAME 运行正常 (端口 $SERVICE_PORT 已监听)"
    exit 0
fi

# 端口异常 → 尝试重启
log "[WARN] $SERVICE_NAME 端口 $SERVICE_PORT 不存在，准备重启..."

# 先优雅停止，再杀残留
call_service "stop"
sleep 1
# 保底：如果 stop 没杀干净，强制清理
pkill -f "$SERVICE_NAME" 2>/dev/null
sleep 2

# 启动 + 重试
attempt=1
while [ $attempt -le "$MAX_RETRY" ]; do
    log "[INFO] 第 $attempt 次启动 $SERVICE_NAME ..."
    call_service "start"

    if wait_port; then
        log "[INFO] $SERVICE_NAME 重启成功 ✓ (端口 $SERVICE_PORT 已监听, 尝试 $attempt 次)"
        exit 0
    fi

    log "[WARN] 第 $attempt 次启动后端口仍未就绪"
    attempt=$((attempt + 1))
    [ $attempt -le "$MAX_RETRY" ] && sleep "$RETRY_INTERVAL"
done

log "[ERROR] $SERVICE_NAME 重启失败 ✗ (已重试 $MAX_RETRY 次)"
exit 1
