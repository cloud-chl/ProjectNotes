#!/bin/bash

if [ $# -lt 1 ];then
  echo "No Args Input..."
  exit;
fi

case $1 in
    "start")
        echo " ============== 启动 Hadoop集群 =============="

        echo "-------------- 启动 hdfs "--------------"
        ssh hadoop01 "/opt/hdoop/sbin/start-dfs.sh"
        echo "-------------- 启动 yarn "--------------"
        ssh hadoop02 "/opt/hdoop/sbin/start-yarn.sh"
        echo "-------------- 启动 historyserver "--------------"
        ssh hadoop01 "/opt/hdoop/bin/mapred --daemon start historyserver.sh"
        ;;
    "stop")
        echo " ============== 关闭 Hadoop集群 =============="

        echo "-------------- 关闭 historyserver "--------------"
        ssh hadoop01 "/opt/hdoop/bin/mapred --daemon stop historyserver.sh"
        echo "-------------- 关闭 yarn "--------------"
        ssh hadoop02 "/opt/hdoop/sbin/stop-yarn.sh"
        echo "-------------- 关闭 hdfs "--------------"
        ssh hadoop01 "/opt/hdoop/sbin/stop-dfs.sh"
        ;;
    *)
        echo "Input Args Error..."
esac