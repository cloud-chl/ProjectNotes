#!/bin/bash
# 用途：手动制造或处理 Kubernetes Pod 的指标，推送到 Prometheus Pushgateway, 让Prometheus Fedration自动Pull数据进行展示

# pushgateway地址
PUSHGATEWAY="http://10.250.122.187:9091"
TOKEN="k8s_token"
METRIC_URL="https://10.250.122.187:10250/metrics"
CLUSTER="cluster-122.187"
NAMESPACE="train-ticket"

# 临时变量存储指标
METRICS_DATA=""

# 获取指标并处理
while IFS= read -r line; do
    # 使用 awk 提取字段并格式化为 Prometheus 行
    formatted_line=$(echo "$line" | awk -v cluster="$CLUSTER" -v ns="$NAMESPACE" '
    match($0, /container="([^"]+)"/, container_match) &&
    match($0, /pod="([^"]+)"/, pod_match) {
        container = container_match[1]
        pod = pod_match[1]
        bytes = $NF
        gib = bytes / (1024^3)
        gib = gib * 10
        # 正确构造 Prometheus 指标格式，注意引号转义
        printf "pod:fs_usage{cluster_id=\"%s\", namespace=\"%s\", pod=\"%s\", container=\"%s\", snc_ingest=\"true\"} %.6f", cluster, ns, pod, container, gib
    }')

    # 累加到 METRICS_DATA
    if [ -n "$formatted_line" ]; then
        METRICS_DATA+="${formatted_line}\n"
    fi

done < <(curl -sSk -H "Authorization: Bearer $TOKEN" "$METRIC_URL" | grep "^kubelet_container_log_filesystem_used_bytes" | grep 'namespace=\"'"$NAMESPACE"'\"')

# 输出指标数据（用于调试或推送到 Pushgateway）
echo -e "$METRICS_DATA" | curl --data-binary @- "$PUSHGATEWAY/metrics/job/pod_fs_usage/instance/$HOSTNAME"
