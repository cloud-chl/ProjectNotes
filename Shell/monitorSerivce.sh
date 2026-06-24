#!/bin/bash
# 用途： 用于监听中间件状态，异常直接重启

# 定义基础路径和日志文件路径
BASE_PATH=/app
LOG_PATH=./monitorService.log

# 声明关联数组，存储服务名称和对应的启动脚本路径及端口
# 格式：服务名 => "脚本路径 端口号"
declare -A services_arr
services_arr=(
    ['zookeeper']="$BASE_PATH/zookeeper/bin/zkServer.sh 2181"
    ['kafka']="$BASE_PATH/kafka/kafka.sh 9092"
)

# 监控服务状态的主函数
monitor_service() {
    # 遍历所有配置的服务
    for service_name in "${!services_arr[@]}"; do
        # 获取值并拆分路径和端口
        # IFS=' ' 设置分隔符为空格，将脚本路径和端口分开
        IFS=' ' read -r script_path service_port <<<"${services_arr[$service_name]}"

        # 检查进程数量：统计包含服务名的进程数量
        process_count=$(ps -ef | grep "$service_name" | wc -l)

        # 检查端口监听状态：查看指定端口是否有进程在监听
        process_port=$(ss -tlnp | grep ":$service_port")

        # 判断服务是否异常：进程数量小于1或端口未监听
        if [ "$process_count" -lt 1 ] || [ -z "$process_port" ]; then
            # 记录服务异常时间
            time=$(date "+%Y-%m-%d %H:%M:%S")
            echo -e "\e[31m$time $service_name is Down.\e[0m" &>>"$LOG_PATH"

            # 尝试启动服务
            start_service "$service_name"

            # 记录启动过程
            time=$(date "+%Y-%m-%d %H:%M:%S")
            echo -e "\e[31m$time $service_name is Starting...\e[0m" &>>"$LOG_PATH"

            # 等待3秒让服务启动
            sleep 3

            # 重新检查进程数量（排除grep进程本身）
            new_process_count=$(ps -ef | grep "$service_name" | wc -l)
            # 更精确的进程计数方法：排除grep进程
            new_process_count=$(ps -ef | grep -v grep | grep -c "$service_name")

            # 重新检查端口监听状态
            new_process_port=$(ss -tlnp | grep ":$service_port")

            # 验证服务是否成功启动
            if [ "$new_process_count" -ge 1 ] && [ -n "$new_process_port" ]; then
                time=$(date "+%Y-%m-%d %H:%M:%S")
                echo -e "\e[31m$time $service_name is Running...\e[0m" &>>"$LOG_PATH"
            fi
        else
            # 服务正常运行，记录状态
            time=$(date "+%Y-%m-%d %H:%M:%S")
            echo -e "\e[31m$time $service_name is Running...\e[0m" &>>"$LOG_PATH"
        fi
    done
}

# 启动服务的函数
start_service() {
    service=$1 # 接收服务名称参数

    # 检查启动脚本是否存在且可执行
    if [ -x "$script_path" ]; then
        # 执行重启命令
        "$script_path" restart
    else
        # 脚本不存在或不可执行，记录错误
        time=$(date "+%Y-%m-%d %H:%M:%S")
        echo -e "\e[31m$time $service script not found or not executable: $script_path\e[0m" &>>"$LOG_PATH"
        return 1
    fi

    # 等待3秒让服务启动
    sleep 3

    # 验证服务是否成功启动
    # 使用pgrep统计进程数量（更准确的方法）
    process_count=$(pgrep -c "$service")
    # 检查端口监听状态
    process_port=$(ss -tlnp | grep "$service")

    # 如果进程数量大于等于1且端口在监听，则认为启动成功
    if [ "$process_count" -ge 1 ] && [ -n "$process_port" ]; then
        time=$(date "+%Y-%m-%d %H:%M:%S")
        echo -e "\e[31m$time $service is Running.\e[0m" &>>"$LOG_PATH"
    fi
}

# 主函数：无限循环监控
main() {
    while true; do
        # 执行监控检查
        monitor_service
        # 每60秒检查一次
        sleep 60
    done
}

# 启动主程序
main
