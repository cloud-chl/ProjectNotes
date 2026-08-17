#!/bin/bash
export PATH="$PATH:/home/shsnc/snc_product/hadoop/bin"
export HADOOP_LOG_DIR=/tmp/dumps/snc-platform-node
export HADOOP_USER_NAME=hdfs
export HADOOP_CONF_DIR=/home/shsnc/snc_product/product/snc-platform-node/yarn-envs/1
export YARN_CONF_DIR=/home/shsnc/snc_product/product/snc-platform-node/yarn-envs/1

LOG_FILE=yarn_application_list.log
KEYWORD="flink-baseline"

# 确保日志输出目录存在
mkdir -p $HADOOP_LOG_DIR

# 获取所有 application 列表（-appStates ALL 才能包含 FINISHED/FAILED/KILLED 等已结束任务，
# 默认只列出 SUBMITTED/ACCEPTED/RUNNING 等非终态任务）
date > $HADOOP_LOG_DIR/$LOG_FILE
yarn app -list -appStates ALL | grep -v -i killed  > $HADOOP_LOG_DIR/$LOG_FILE

# 只处理以 application_ 开头的行（跳过表头），限制为24个任务（每小时一个）：
count=0
max_count=24

while read -r appId appName rest; do

    [ -z "$appId" ] && continue
    # 计数器，达到24个后退出
    count=$((count + 1))

    if [ $count -gt $max_count ]; then
        echo "已达到最大任务数量 $max_count，停止处理"
        break
    fi

    echo "正在处理第 $count/$max_count 个任务: $appId"
    
    # 替换文件名中不合法的字符，避免创建文件失败
    safeName=$(echo "$appName" | sed 's/[\/\\:*?"<>|[:space:]]/_/g')
    yarn logs -applicationId "$appId" > "$HADOOP_LOG_DIR/${appId}_${safeName}.log"

done < <(grep '^application_' $HADOOP_LOG_DIR/$LOG_FILE | grep -i "$KEYWORD")
