#!/bin/bash
# 用途： 用于监听中间件状态，异常直接重启

time=$(date "+%Y-%m-%d %H:%M:%S")
BASE_PATH=/app/product
LOG_PATH=/var/log/monitor_service.log
declare -A service_arr
service_arr=(['minio']=9900 ['nacos']=8848 ['nginx']=8080)

monitor_service() {
    for service_name in "${!service_arr[@]}"; do
        process_count=$(pgrep -c "$service_name")
        process_port=$(ss -tlnp | grep "$service_name")

        if [ "$process_count" -lt 1 ] || [ -z "$process_port" ]; then
            echo -e "\e[31m$time $service_name is Down.\e[0m" &>>"$LOG_PATH"
            start_service "$service_name"
            echo -e "\e[31m$time $service_name is Starting...\e[0m" &>>"$LOG_PATH"
            sleep 3
            # 重新获取进程数量和端口信息
            new_process_count=$(ps -ef | grep -v grep | grep -c "$service_name")
            new_process_port=$(ss -tlnp | grep "${service_name[$service_name]}")
            if [ "$new_process_count" -gt 1 ] && [ -n "$new_process_port" ]; then
                echo -e "\e[31m$time $service_name is Running...\e[0m" &>>"$LOG_PATH"
            fi
        else
            echo -e "\e[31m$time $service_name is Running...\e[0m" &>>"$LOG_PATH"
        fi
    done
}

start_service() {
    service=$1
    "$BASE_PATH"/"$service"/"$service".sh restart
    sleep 3
    process_count=$(pgrep -c "$service")
    process_port=$(ss -tlnp | grep "$service")
    if [ "$process_count" -gt 1 ] && [ -n "$process_port" ]; then
        echo -e "\e[31m$time $service is Running.\e[0m" &>>"$LOG_PATH"
    fi

}

main() {
    while true; do
        monitor_service
        sleep 60
    done
}

main
