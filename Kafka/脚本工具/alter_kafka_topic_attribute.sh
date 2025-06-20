#!/bin/bash

# ================== 配置参数 ==================
KAFKA_BIN="/home/shsnc/snc_product/kafka/bin"        # 替换为你的 Kafka 安装目录下的 bin 文件夹
ZK_SERVER="192.168.1.1:2181"                         # Zookeeper 地址，低版本需要
BOOTSTRAP_SERVER="192.168.1.1:9092"                  # Kafka Broker 地址
RETENTION_MS="86400000"                              # 保留时间：24小时（单位：毫秒）
SEGMENT_BYTES="536870912"                            # 推荐值：512MB（可选）
# ==============================================

# 获取所有 Topic 名称
ALL_TOPICS=$("${KAFKA_BIN}/kafka-configs.sh" --bootstrap-server "${BOOTSTRAP_SERVER}" --list)

# 要修改的 Topic 列表（包括通配符）
TOPICS=(
  topic1
  topic2
  topic3
)

# 扩展通配符 Topic 名称
EXPANDED_TOPICS=()
for pattern in "${TOPICS[@]}"; do
    if [[ "$pattern" == *"*"* ]]; then
        for topic in $ALL_TOPICS; do
            if [[ "$topic" == $pattern ]]; then
                EXPANDED_TOPICS+=("$topic")
            fi
        done
    else
        EXPANDED_TOPICS+=("$pattern")
    fi
done

# 遍历每个 Topic
for topic in "${EXPANDED_TOPICS[@]}"; do
    if [[ -z "$topic" ]]; then
        continue
    fi

    echo "正在修改 Topic: ${topic}"

    # 设置 retention.ms
    "${KAFKA_BIN}/kafka-configs.sh" \
        --zookeeper "${ZK_SERVER}" \
        --alter \
        --entity-type topics \
        --entity-name "${topic}" \
        --add-config retention.ms="${RETENTION_MS}"

    if [ $? -ne 0 ]; then
        echo "Topic '${topic}' 修改 retention.ms 失败"
        continue
    else
        echo "Topic '${topic}' retention.ms 设置成功"
    fi  

    # 如果设置了 segment.bytes，则添加
    if [ -n "${SEGMENT_BYTES}" ]; then
        "${KAFKA_BIN}/kafka-configs.sh" \
        --zookeeper "${ZK_SERVER}" \
        --alter \
        --entity-type topics \
        --entity-name "${topic}" \
        --add-config segment.bytes="${SEGMENT_BYTES}"

        if [ $? -ne 0 ]; then
            echo "Topic '${topic}' 修改 segment.bytes 失败"
        else
            echo "Topic '${topic}' segment.bytes 设置成功"
        fi
    fi
done