#!/bin/bash

# 启动用户
USER=root
# 服务名称
SERVICE_NAME="clickhouse-server"
# 服务路径
SERVICE_PATH=/root/clickhouse
# 服务可执行文件
SERVICE_BIN=$SERVICE_PATH/bin/clickhouse-server
# 服务配置文件
SERVICE_CONF=$SERVICE_PATH/etc/config.xml
# 服务端口
SERVICE_PORT=9000
# 服务启动脚本
SH_FILE=clickhouse.sh
# 服务启动命令
$START_COMMAND="$SERVICE_BIN --config-file $SERVICE_CONF --pid-file ${SERVICE_PATH}/logs/clickhouse-server.pid --daemon"

# 获取进程数量
get_process_count(){
    ps -ef | grep -i "$SERVICE_NAME" | grep -v grep | grep -v $SH_FILE | wc -l
}

# 获取进程ID
get_process_num(){
    ps -ef | grep -i "$SERVICE_NAME" | grep -v grep | grep -v $SH_FILE | awk '{print $2}'
}

# 获取端口信息
get_port_info(){
    ss -tlnp | grep ":$SERVICE_PORT"
}

start(){
    local process=$(get_process_count)

    if [ $process -gt 0 ];then
        echo "$SERVICE_NAME is Already Running."
        return 0
    else
        $START_COMMAND
        sleep 3

        local process_port=$(get_port_info)
        local process_id=$(get_process_num)
        local process_num=$(get_process_count)

        # 启动成功诊断信息
        if [ -n "$process_port" ] && [ -n "$process_id" ] && [ "$process_num" -gt 0 ]; then
            echo "$SERVICE_NAME is Started, PID: $pid"
            return 0
        else
            # 启动失败诊断信息
            echo "$SERVICE_NAME startup failed. Diagnostics:"
            [ -z "$pid" ] && echo " - No process found"
            [ -z "$port_info" ] && echo " - Port $SERVICE_PORT not listening"
            [ $process_count -eq 0 ] && echo " - Process exited immediately"
            return 1
        fi
    fi
}

stop(){
    local process=$(get_process_count)
    local pid=$(get_process_num)
    if [ $process -gt 0 ];then
        kill -15 $pid

        sleep 3
        if [ ! -s "$SERVICE_PID_FILE" ]; then
            echo "$SERVICE_NAME is stopped."
            return 0
        fi
    fi
}

status(){
    local info=$(get_port_info)
    local pid=$(get_process_num)
    
    if [ -s "$SERVICE_PID_FILE" ] || [ -n "$info" ]; then
        echo "$SERVICE_NAME is Already Running, PID: $pid"
        return 0
    else
        echo "$SERVICE_NAME is Not Running."
    fi
}


case $1 in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        start
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
