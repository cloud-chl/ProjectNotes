#!/bin/bash
# rsync_pull_artifacts.sh
# 把远端 test/prod 各项目下的 lib 包和 jar 包拉取到本地
#
# 远端结构示例：
#   /data/test/snc-ng-server/{lib/, snc-ng-server.jar, config/, logs/ ...}
#   /data/prod/snc-ng-server/{lib/, snc-ng-server.jar, ...}
# 拉取内容（只拉这些）：
#   每个项目按配置区 DEFAULT_INCLUDES 的模式拉取（默认 lib/*** + *.jar），
#   其他文件（config、Dockerfile、logs 等）不拉取
#   特殊项目例外（配置区 SPECIAL_INCLUDES）：例如 nginx 拉取 @project 和 web_root 目录
# 本地目录结构与远端保持一致：本地 $LOCAL_BASE 对应远端 $REMOTE_BASE
#
# 前提：本机已配置到远端的 ssh 免密（本机执行 ssh-copy-id $REMOTE_HOST）
#
# 用法：
#   ./rsync_pull_artifacts.sh --dry-run    # 先预览拉取内容，不实际同步
#   ./rsync_pull_artifacts.sh              # 实际拉取
#   crontab 定时： */30 * * * * /path/to/rsync_pull_artifacts.sh
#
# 注意：增量拉取，远端已删除的旧 jar 不会在本地删除

set -o pipefail

# ============ 配置区 ============
REMOTE_HOST="root@172.16.1.3"      # 远端地址：user@host 或 host
SSH_PORT=2222
SSH_OPTS="-o BatchMode=yes -o StrictHostKeyChecking=accept-new"  # ssh 附加选项：免密没配好直接报错不卡住等密码；新主机自动接受 host key
REMOTE_BASE="/data"                # 远端根目录（下有 test/ prod/）
LOCAL_BASE="/home/cai"             # 本地根目录，结构与远端对应
SYNC_DIRS=("test" "prod")          # 需要拉取的子目录

# 默认拉取规则：所有项目（特殊项目除外）统一按这些模式拉取，后续调整/追加直接改这里
DEFAULT_INCLUDES=(
    "lib/***"      # lib 目录及全部内容
    "*.jar"        # 任意位置的 jar 包
)
DEFAULT_EXCLUDES=(
    "jdk/"         # jdk 目录整个排除（JDK 自带 jar 很大，一般不用同步）
)

# 特殊项目拉取规则：个别项目结构不同，单独指定要拉的内容（相对项目目录的 rsync include 模式）
# 默认所有项目按 DEFAULT_INCLUDES 拉取；这里列出的项目按自己的规则拉取，不再套用默认规则
# 键=项目目录名，值=要拉取的目录/文件模式（多个用空格分隔），例如 nginx：
#   [nginx]="--include='@project/***' --include='web_root/***'"
declare -A SPECIAL_INCLUDES=(
    [nginx]="--include='@project/***' --include='web_root/***'"
)

RSYNC_OPTS="-avzm"                 # a=归档保留属性 v=详细 z=压缩 m=清理被过滤掉的空目录
LOG_FILE="/var/log/rsync_pull_artifacts.log"
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

# ---------- 参数解析 ----------

DRY_RUN=""
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run)  DRY_RUN="--dry-run"; shift ;;
        -h|--help)  usage ;;
        *)          log "[ERROR] 未知选项: $1"; usage ;;
    esac
done

command -v rsync >/dev/null 2>&1 || { echo "[ERROR] 未找到 rsync 命令"; exit 1; }

log_rotate
log "[INFO] ========== 开始拉取 =========="
FAIL=0

# ---------- 1. 默认规则拉取（模式见配置区 DEFAULT_INCLUDES / DEFAULT_EXCLUDES） ----------
# 组装过滤规则（先匹配先生效）：
#   特殊项目排除 -> 默认排除项（jdk/ 等）-> 所有目录进入 -> 默认拉取模式 -> 其余一律排除
PULL_FILTERS=""
for name in "${!SPECIAL_INCLUDES[@]}"; do
    PULL_FILTERS="$PULL_FILTERS --exclude='$name/'"
done
for pat in "${DEFAULT_EXCLUDES[@]}"; do
    PULL_FILTERS="$PULL_FILTERS --exclude='$pat'"
done
PULL_FILTERS="$PULL_FILTERS --include='*/'"
for pat in "${DEFAULT_INCLUDES[@]}"; do
    PULL_FILTERS="$PULL_FILTERS --include='$pat'"
done
PULL_FILTERS="$PULL_FILTERS --exclude='*'"

for env in "${SYNC_DIRS[@]}"; do
    log "[INFO] 拉取 $env : $REMOTE_HOST:$REMOTE_BASE/$env -> $LOCAL_BASE/$env"

    CMD="rsync $RSYNC_OPTS -e \"ssh -p $SSH_PORT $SSH_OPTS\" $DRY_RUN $PULL_FILTERS \"$REMOTE_HOST:$REMOTE_BASE/$env/\" \"$LOCAL_BASE/$env/\""
    log "[INFO] 执行: $CMD"

    if eval "$CMD" >> "$LOG_FILE" 2>&1; then
        log "[INFO] 拉取完成 ✓ ($env)"
    else
        log "[ERROR] 拉取失败 ✗ ($env)，rsync 输出如下:"
        tail -n 5 "$LOG_FILE" | while read -r line; do log "  | $line"; done
        FAIL=1
    fi
done

# ---------- 2. 特殊项目拉取（SPECIAL_INCLUDES 里的项目） ----------
for name in "${!SPECIAL_INCLUDES[@]}"; do
    for env in "${SYNC_DIRS[@]}"; do
        # 远端不存在该项目的环境目录则跳过
        if ! ssh -p "$SSH_PORT" $SSH_OPTS "$REMOTE_HOST" "test -d '$REMOTE_BASE/$env/$name'" >> "$LOG_FILE" 2>&1; then
            log "[WARN] 远端不存在 $env/$name，跳过"
            continue
        fi
        log "[INFO] 拉取 $env/$name (特殊规则) : $REMOTE_HOST:$REMOTE_BASE/$env/$name -> $LOCAL_BASE/$env/$name"

        CMD="rsync $RSYNC_OPTS -e \"ssh -p $SSH_PORT $SSH_OPTS\" $DRY_RUN --include='*/' ${SPECIAL_INCLUDES[$name]} --exclude='*' \"$REMOTE_HOST:$REMOTE_BASE/$env/$name/\" \"$LOCAL_BASE/$env/$name/\""
        log "[INFO] 执行: $CMD"

        if eval "$CMD" >> "$LOG_FILE" 2>&1; then
            log "[INFO] 拉取完成 ✓ ($env/$name)"
        else
            log "[ERROR] 拉取失败 ✗ ($env/$name)，rsync 输出如下:"
            tail -n 5 "$LOG_FILE" | while read -r line; do log "  | $line"; done
            FAIL=1
        fi
    done
done

if [ $FAIL -eq 0 ]; then
    log "[INFO] 全部拉取完成 ✓"
    exit 0
else
    log "[ERROR] 存在失败的同步项 ✗"
    exit 1
fi
