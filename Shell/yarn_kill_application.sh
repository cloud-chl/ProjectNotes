#!/bin/bash

export PATH="$PATH:/home/shsnc/snc_product/hadoop/bin"
export HADOOP_LOG_DIR=/tmp/dumps/snc-platform-node
export HADOOP_USER_NAME=hdfs
export HADOOP_CONF_DIR=/home/shsnc/snc_product/product/snc-platform-node/yarn-envs/1
export YARN_CONF_DIR=/home/shsnc/snc_product/product/snc-platform-node/yarn-envs/1

# ===== 可配置项 =====
KEYWORD="flink-baseline"  # applicationName 中要匹配的关键字（不区分大小写）
DRY_RUN=false             # true=只打印将要 kill 的任务，不真正 kill；false=真正执行 kill
DEBUG=true                # true=同时输出调试信息到控制台（排查容器环境 yarn 命令问题用）
# ====================

mkdir -p "$HADOOP_LOG_DIR"
LOG_FILE="$HADOOP_LOG_DIR/kill_${KEYWORD}.log"
: > "$LOG_FILE"            # 每次运行重置日志
date > "$LOG_FILE"
# 只输出到日志文件（不输出到控制台）
log() { echo "$*" >> "$LOG_FILE"; }

# 1) 只看活跃状态（RUNNING + ACCEPTED），因为：
#    - 任务有超时时间，且同时只能运行 1 个
#    - 如果出现多个活跃任务，说明有人重复提交了，只保留最新的（ID 最大）
#    - 已经 KILLED/FINISHED/FAILED 的不参与判断，避免干扰
YARN_OUTPUT=$(yarn application -list -appStates RUNNING,ACCEPTED 2>&1)
YARN_RC=$?
if [ "$DEBUG" = "true" ]; then
    echo "=== DEBUG: yarn application -list 原始输出（退出码=$YARN_RC）==="
    echo "$YARN_OUTPUT"
    echo "=== DEBUG END ==="
fi
mapfile -t ACTIVE_IDS < <(echo "$YARN_OUTPUT" \
    | grep '^application_' \
    | grep -i "$KEYWORD" \
    | awk '{print $1}')

if [ ${#ACTIVE_IDS[@]} -eq 0 ]; then
    log "未找到 applicationName 包含 [$KEYWORD] 的活跃任务（RUNNING/ACCEPTED）。"
    exit 0
fi

# 按 application ID 降序排列（_xxxx 序号越大越新）
# 注意：不用 sort -n，因为 YARN ID 的序号是定宽补零的（_0123），字典反序即可；
#       某些系统的 sort 在 -t/-k/-n/-r 组合时有 bug 导致反转失效
mapfile -t SORTED_IDS < <(printf '%s\n' "${ACTIVE_IDS[@]}" | sort -r)

KEEP_ID="${SORTED_IDS[0]}"          # 保留最新的（ID 最大）
KILL_IDS=("${SORTED_IDS[@]:1}")     # 其余旧的活跃任务全部 kill

if [ ${#KILL_IDS[@]} -eq 0 ]; then
    log "仅 1 个活跃任务 [$KEEP_ID]，无需 kill。"
    exit 0
fi

log "活跃任务（RUNNING/ACCEPTED）共 ${#ACTIVE_IDS[@]} 个，保留最新 [$KEEP_ID]，将 kill 其余 ${#KILL_IDS[@]} 个旧任务（DRY_RUN=$DRY_RUN）："
log "  保留: $KEEP_ID"
printf '  kill: %s\n' "${KILL_IDS[@]}" >> "$LOG_FILE"
log "----------------------------------------"

# 3) 逐个 kill
for appId in "${KILL_IDS[@]}"; do
    if [ "$DRY_RUN" = "true" ]; then
        log "[DRY_RUN] 将 kill: $appId"
    else
        log "正在 kill: $appId"
        yarn application -kill "$appId" >> "$LOG_FILE" 2>&1
    fi
done
