#!/bin/bash
# rsync_push_artifacts.sh
# 把本地 test/prod 各项目目录下的指定文件（默认 Dockerfile*）推送到远端
#
# 推送内容：
#   本地 $LOCAL_BASE/{test,prod} 下每个项目目录里匹配 PUSH_INCLUDES 模式的文件
#   （默认 Dockerfile*，即 Dockerfile、Dockerfile_test 等），
#   推到远端 $REMOTE_BASE 下相同的 环境/项目 目录；
#   PUSH_ITEMS 中列出的指定文件/目录也会推送
#
# 前提：本机已配置到远端的 ssh 免密（本机执行 ssh-copy-id $REMOTE_HOST）
#
# 用法：
#   ./rsync_push_artifacts.sh --dry-run    # 先预览传输内容，不实际推送
#   ./rsync_push_artifacts.sh              # 实际推送
#   crontab 定时： */30 * * * * /path/to/rsync_push_artifacts.sh
#
# 注意：推送只覆盖匹配的文件，项目里其他文件不受影响；不会删除远端任何文件

set -o pipefail

# ============ 配置区 ============
REMOTE_HOST="root@172.16.1.3"      # 远端地址：user@host 或 host
SSH_PORT=2222
SSH_OPTS="-o BatchMode=yes -o StrictHostKeyChecking=accept-new"  # ssh 附加选项：免密没配好直接报错不卡住等密码；新主机自动接受 host key
REMOTE_BASE="/data"                # 远端根目录（下有 test/ prod/）
LOCAL_BASE="/home/cai"             # 本地根目录，结构与远端对应
SYNC_DIRS=("test" "prod")          # 需要推送扫描的子目录

# 按模式推送：本地每个项目目录下匹配这些模式的文件，推到远端相同项目目录
# 新增要推送的文件直接往数组里追加即可，例如：
#   "entrypoint.sh"   单个文件名（项目目录内任意层级都匹配）
#   "*.sh"            通配符模式（* 可以跨目录匹配）
#   "config/***"      整个目录及其内容（rsync 的 *** 表示目录下所有内容）
PUSH_INCLUDES=(
    "Dockerfile*"      # 默认 Dockerfile、Dockerfile_test 等
    "entrypoint.sh"
    "config/***"
    "scripts/***"
    "cron-config"
    "logs/***"
)
# 按列表推送：指定路径的文件/目录（相对 LOCAL_BASE 的路径，不要写绝对路径），留空则不推
PUSH_ITEMS=(
    "test/alone_build.sh"
    "prod/alone_build.sh"
    "test/nginx/lua"
)

RSYNC_OPTS="-avzm"                 # a=归档保留属性 v=详细 z=压缩 m=清理被过滤掉的空目录
LOG_FILE="/var/log/rsync_push_artifacts.log"
MAX_LOG_SIZE=$((10 * 1024 * 1024)) # 日志超过 10MB 自动轮转
# =================================

# ---------- 工具函数 ----------

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg" >> "$LOG_FILE"
    echo "$msg"
}

log_rotate() {
    if [ -f "$LOG_FILE" ] && [ "$(stat -c%s "$LOG_FILE" 2>/dev/null || stat -f%z "$LOG_FILE" 2>/dev/null || echo 0)" -ge "$MAX_LOG_SIZE" ]; then
        mv "$LOG_FILE" "${LOG_FILE}.1"
    fi
}

usage() {
    grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -30
    exit 1
}

# 执行一条 rsync 命令，日志落盘，失败返回 1
run_rsync() {
    log "[INFO] 执行: $1"
    if eval "$1" >> "$LOG_FILE" 2>&1; then
        return 0
    else
        log "[ERROR] 执行失败 ✗，rsync 输出如下:"
        tail -n 5 "$LOG_FILE" | while read -r line; do log "  | $line"; done
        return 1
    fi
}

# ---------- 参数解析 ----------

DRY_RUN=""
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)  DRY_RUN="--dry-run"; shift ;;
        -h|--help)  usage ;;
        *)          log "[ERROR] 未知选项: $1"; usage ;;
    esac
done

command -v rsync >/dev/null 2>&1 || { log "[ERROR] 未找到 rsync 命令"; exit 1; }

log_rotate
log "[INFO] ========== 开始推送 =========="
FAIL=0

# ---------- 1. 按模式推送：每个项目目录下匹配 PUSH_INCLUDES 的文件 ----------
for env in "${SYNC_DIRS[@]}"; do
    for proj_dir in "$LOCAL_BASE/$env"/*/; do
        [ -d "$proj_dir" ] || continue
        proj="$(basename "$proj_dir")"

        # 项目里没有任何匹配文件则跳过
        found=""
        for pat in "${PUSH_INCLUDES[@]}"; do
            [ -n "$(find "$proj_dir" -name "$pat" -print -quit 2>/dev/null)" ] && found=1 && break
        done
        [ -z "$found" ] && continue

        # 过滤规则：目录进入 -> 匹配模式的文件推送 -> 其余排除
        INCS="--include='*/'"
        for pat in "${PUSH_INCLUDES[@]}"; do
            INCS="$INCS --include='$pat'"
        done
        log "[INFO] 推送 $env/$proj (${PUSH_INCLUDES[*]}) -> $REMOTE_HOST:$REMOTE_BASE/$env/$proj"
        CMD="rsync $RSYNC_OPTS -e \"ssh -p $SSH_PORT $SSH_OPTS\" $DRY_RUN $INCS --exclude='*' \"$LOCAL_BASE/$env/$proj/\" \"$REMOTE_HOST:$REMOTE_BASE/$env/$proj/\""
        run_rsync "$CMD" || { log "[ERROR] 推送失败 ✗ ($env/$proj)"; FAIL=1; }
    done
done

# ---------- 2. 按列表推送：PUSH_ITEMS 指定的文件/目录 ----------
for item in "${PUSH_ITEMS[@]}"; do
    [ -z "$item" ] && continue
    if [ ! -e "$LOCAL_BASE/$item" ]; then
        log "[ERROR] 本地不存在: $LOCAL_BASE/$item，跳过"
        FAIL=1
        continue
    fi
    log "[INFO] 推送: $LOCAL_BASE/$item -> $REMOTE_HOST:$REMOTE_BASE/$item"
    # -R 保留相对路径：远端按相同路径存放，中间目录不存在会自动创建
    CMD="rsync $RSYNC_OPTS -R -e \"ssh -p $SSH_PORT $SSH_OPTS\" $DRY_RUN \"$LOCAL_BASE/./$item\" \"$REMOTE_HOST:$REMOTE_BASE/\""
    run_rsync "$CMD" && log "[INFO] 推送完成 ✓ ($item)" || { log "[ERROR] 推送失败 ✗ ($item)"; FAIL=1; }
done

if [ $FAIL -eq 0 ]; then
    log "[INFO] 全部推送完成 ✓"
    exit 0
else
    log "[ERROR] 存在失败的推送项 ✗"
    exit 1
fi
