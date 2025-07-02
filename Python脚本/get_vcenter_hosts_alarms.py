from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
import ssl
import sys
import warnings
import json
from kafka import KafkaProducer
from datetime import datetime

# 忽略 SSL 弃用警告
warnings.filterwarnings(
    "ignore", category=DeprecationWarning, message="ssl.PROTOCOL_TLSv1 is deprecated"
)

# kafka配置
kafka_bootstrap_servers = "192.168.1.1:9092"
kafka_host_topic = "venter_hosts"
kafka_alarm_topic = "vcenter_alarms"

# vcenter配置
vcenter_ip = "192.168.1.1"
vcenter_port = 443
username = "administrator@vsphere.local"
password = "admin@123"


def write_to_file(subject, list_info, filename=None):
    """将宿主机信息写入JSON文件"""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"vsphere_{subject}_{timestamp}.json"

    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(list_info, f, ensure_ascii=False, indent=2)
        print(f"宿主机信息已保存到文件: {filename}")
        return filename
    except Exception as e:
        print(f"写入文件失败: {e}", file=sys.stderr)
        return None


def write_to_kafka(subject, list_info, kafka_bootstrap_servers, topic):
    """将信息发送到Kafka
    subject: 主题, 区分宿主机信息和警报信息
    list_info: 信息列表, 如宿主机信息列表, 警报信息列表
    kafka_bootstrap_servers: kafka服务器地址
    topic: kafka主题
    """
    try:
        producer = KafkaProducer(
            bootstrap_servers=kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode(
                "utf-8"
            ),
        )
        producer.send(topic, value=list_info)
        producer.flush()
        producer.close()
        print(f"已将{subject}发送到Kafka topic: {topic}")
        return True
    except Exception as e:
        print(f"发送到Kafka失败: {e}", file=sys.stderr)
        return False


def get_hosts_info(content):
    """获取vSphere 6.5环境中所有宿主机信息"""
    host_view = content.viewManager.CreateContainerView(
        content.rootFolder, [vim.HostSystem], True
    )
    hosts = host_view.view
    host_view.Destroy()

    hosts_info_list = []
    for host in hosts:
        host_info = {
            "HOST_NAME": host.name,
            "CONNECTION_STATE": (
                host.runtime.connectionState
                if hasattr(host.runtime, "connectionState")
                else "N/A"
            ),
            "MAINTENANCE_MODE": (
                host.runtime.inMaintenanceMode
                if hasattr(host.runtime, "inMaintenanceMode")
                else "N/A"
            ),
        }
        # 获取产品信息
        if (
            hasattr(host, "summary")
            and host.summary
            and hasattr(host.summary, "config")
        ):
            config = host.summary.config
            host_info.update(
                {
                    "PRODUCT_VERSION": (
                        config.product.version if hasattr(config, "product") else "N/A"
                    ),
                    "PRODUCT_NAME": (
                        config.product.name if hasattr(config, "product") else "N/A"
                    ),
                    "PRODUCT_VENDOR": (
                        config.product.vendor if hasattr(config, "product") else "N/A"
                    ),
                }
            )
        else:
            host_info.update(
                {
                    "PRODUCT_VERSION": "N/A",
                    "PRODUCT_NAME": "N/A",
                    "PRODUCT_VENDOR": "N/A",
                }
            )

        # 获取硬件信息
        hardware = getattr(host, "hardware", None)
        if hardware:
            # CPU信息 - vSphere 6.5兼容
            cpu_info = getattr(hardware, "cpuInfo", None)
            if cpu_info:
                # 尝试多种方式获取CPU型号
                cpu_model = "N/A"
                if hasattr(cpu_info, "model"):
                    cpu_model = cpu_info.model
                elif hasattr(cpu_info, "cpuModel"):
                    cpu_model = cpu_info.cpuModel
                elif hasattr(cpu_info, "vendor"):
                    cpu_model = cpu_info.vendor

                host_info.update(
                    {
                        "CPU_MODEL": cpu_model,
                        "CPU_CORES": cpu_info.numCpuCores,
                        "CPU_THREADS": cpu_info.numCpuThreads,
                        "CPU_FREQUENCY": cpu_info.hz / 1000000,
                    }
                )
            else:
                host_info.update(
                    {
                        "CPU_MODEL": "N/A",
                        "CPU_CORES": "N/A",
                        "CPU_THREADS": "N/A",
                        "CPU_FREQUENCY": "N/A",
                    }
                )

            # 内存信息
            host_info["MEMORY_TOTAL"] = round(hardware.memorySize / (1024**3), 2)
        else:
            host_info.update(
                {
                    "CPU_MODEL": "N/A",
                    "CPU_CORES": "N/A",
                    "CPU_THREADS": "N/A",
                    "CPU_FREQUENCY": "N/A",
                    "MEMORY_TOTAL": "N/A",
                }
            )

        # 获取runtime信息
        runtime_info = {}
        if hasattr(host, "runtime") and host.runtime:
            runtime = host.runtime

            # 基本runtime信息
            runtime_info.update(
                {
                    "POWER_STATE": (
                        str(runtime.powerState)
                        if hasattr(runtime, "powerState")
                        else "N/A"
                    ),
                    "STANDBY_MODE": (
                        runtime.standbyMode
                        if hasattr(runtime, "standbyMode")
                        else "N/A"
                    ),
                    "QUARANTINE_MODE": (
                        runtime.inQuarantineMode
                        if hasattr(runtime, "inQuarantineMode")
                        else "N/A"
                    ),
                    "BOOT_TIME": (
                        runtime.bootTime.isoformat()
                        if hasattr(runtime, "bootTime") and runtime.bootTime
                        else "N/A"
                    ),
                }
            )

            # HA集群状态信息
            if hasattr(runtime, "dasHostState"):
                das_state = runtime.dasHostState
                if das_state:
                    runtime_info.update(
                        {
                            "HA_CLUSTER_STATE": (
                                str(das_state.state)
                                if hasattr(das_state, "state")
                                else "N/A"
                            ),
                            "HA_CLUSTER_STATE_DETAILS": (
                                das_state.stateDetails
                                if hasattr(das_state, "stateDetails")
                                else "N/A"
                            ),
                        }
                    )
                else:
                    runtime_info.update(
                        {
                            "HA_CLUSTER_STATE": "N/A",
                            "HA_CLUSTER_STATE_DETAILS": "N/A",
                        }
                    )
            else:
                runtime_info.update(
                    {
                        "HA_CLUSTER_STATE": "N/A",
                        "HA_CLUSTER_STATE_DETAILS": "N/A",
                    }
                )

            # 加密状态信息 (vSphere 6.5+)
            if hasattr(runtime, "cryptoState"):
                runtime_info["ENCRYPTION_STATE"] = runtime.cryptoState
            else:
                runtime_info["ENCRYPTION_STATE"] = "N/A"

            # 最大虚拟磁盘容量
            if hasattr(runtime, "hostMaxVirtualDiskCapacity"):
                max_capacity = runtime.hostMaxVirtualDiskCapacity
                if max_capacity:
                    runtime_info["MAX_VIRTUAL_DISK_CAPACITY"] = round(
                        max_capacity / (1024**3), 2
                    )
                else:
                    runtime_info["MAX_VIRTUAL_DISK_CAPACITY"] = "N/A"
            else:
                runtime_info["MAX_VIRTUAL_DISK_CAPACITY"] = "N/A"

            # 网络runtime信息
            if hasattr(runtime, "networkRuntimeInfo") and runtime.networkRuntimeInfo:
                network_runtime = runtime.networkRuntimeInfo
                runtime_info.update(
                    {
                        "NETWORK_CONNECTED_COUNT": (
                            network_runtime.connectedVnicCount
                            if hasattr(network_runtime, "connectedVnicCount")
                            else "N/A"
                        ),
                        "NETWORK_DISCONNECTED_COUNT": (
                            network_runtime.disconnectedVnicCount
                            if hasattr(network_runtime, "disconnectedVnicCount")
                            else "N/A"
                        ),
                    }
                )
            else:
                runtime_info.update(
                    {
                        "NETWORK_CONNECTED_COUNT": "N/A",
                        "NETWORK_DISCONNECTED_COUNT": "N/A",
                    }
                )

            # vSAN runtime信息
            if hasattr(runtime, "vsanRuntimeInfo") and runtime.vsanRuntimeInfo:
                vsan_runtime = runtime.vsanRuntimeInfo
                runtime_info.update(
                    {
                        "VSAN_STATE": (
                            str(vsan_runtime.state)
                            if hasattr(vsan_runtime, "state")
                            else "N/A"
                        ),
                        "VSAN_NODE_UUID": (
                            vsan_runtime.nodeUuid
                            if hasattr(vsan_runtime, "nodeUuid")
                            else "N/A"
                        ),
                    }
                )
            else:
                runtime_info.update(
                    {
                        "VSAN_STATE": "N/A",
                        "VSAN_NODE_UUID": "N/A",
                    }
                )

            # vFlash runtime信息
            if (
                hasattr(runtime, "vFlashResourceRuntimeInfo")
                and runtime.vFlashResourceRuntimeInfo
            ):
                vflash_runtime = runtime.vFlashResourceRuntimeInfo
                runtime_info.update(
                    {
                        "VFLASH_CAPACITY": (
                            round(vflash_runtime.capacity / (1024**3), 2)
                            if hasattr(vflash_runtime, "capacity")
                            else "N/A"
                        ),
                        "VFLASH_FREE_CAPACITY": (
                            round(vflash_runtime.freeCapacity / (1024**3), 2)
                            if hasattr(vflash_runtime, "freeCapacity")
                            else "N/A"
                        ),
                    }
                )
            else:
                runtime_info.update(
                    {
                        "VFLASH_CAPACITY": "N/A",
                        "VFLASH_FREE_CAPACITY": "N/A",
                    }
                )

        host_info["RUNTIME_INFO"] = runtime_info

        # 获取存储信息 - 针对vSphere 6.5优化
        storage_info = []
        try:
            # 方法1：通过数据存储获取（推荐方法）
            datastores = host.datastore
            for ds in datastores:
                try:
                    storage_info.append(
                        {
                            "Volume": ds.name,
                            "Type": ds.summary.type,
                            "Capacity(GB)": round(ds.summary.capacity / (1024**3), 2),
                            "Free(GB)": round(ds.summary.freeSpace / (1024**3), 2),
                        }
                    )
                except Exception as e:
                    print(f"处理数据存储 {ds.name} 时出错: {str(e)}", file=sys.stderr)
                    storage_info.append(
                        {
                            "Volume": ds.name,
                            "Type": "Unknown",
                            "Capacity(GB)": "N/A",
                            "Free(GB)": "N/A",
                        }
                    )
        except Exception as e:
            print(f"通过数据存储获取信息时出错: {str(e)}", file=sys.stderr)

        # 如果以上方法都失败，提供错误信息
        if not storage_info:
            storage_info.append({"error": "无法获取存储信息"})

        host_info["STORAGE_VOLUMES"] = storage_info

        # 获取网络信息
        network_info = []
        pnics = []
        try:
            network_system = host.configManager.networkSystem
            if network_system:
                # 获取物理网卡
                pnics = (
                    [nic.device for nic in network_system.networkInfo.pnic]
                    if hasattr(network_system.networkInfo, "pnic")
                    else []
                )

                # 获取虚拟交换机
                if hasattr(network_system.networkInfo, "vswitch"):
                    for net in network_system.networkInfo.vswitch:
                        network_info.append(
                            {"VSWITCH": net.name, "PORTS": net.numPorts, "MTU": net.mtu}
                        )
        except Exception as e:
            print(f"获取网络信息时出错: {str(e)}", file=sys.stderr)
            # 回退到旧方法
            if (
                hasattr(host, "config")
                and host.config
                and hasattr(host.config, "network")
            ):
                config = host.config
                if hasattr(config.network, "pnic"):
                    pnics = [nic.device for nic in config.network.pnic]
                if hasattr(config.network, "vswitch"):
                    for net in config.network.vswitch:
                        network_info.append(
                            {"VSWITCH": net.name, "PORTS": net.numPorts, "MTU": net.mtu}
                        )

        host_info["NETWORK_ADAPTERS"] = pnics
        host_info["VIRTUAL_SWITCHES"] = network_info
        hosts_info_list.append(host_info)

    return hosts_info_list


def get_alarm_info(content):
    """获取vCenter中的已触发告警信息"""
    try:
        # 获取当前时间
        current_time = datetime.now().isoformat()
        contents = (
            content.RetrieveContent()
            if hasattr(content, "RetrieveContent")
            else content
        )
        alarm_contents = contents.rootFolder.triggeredAlarmState
        alarms_info_list = []
        for triggered_alarm in alarm_contents:
            try:
                alarm_data = {
                    "ALARM_NAME": (
                        triggered_alarm.alarm.info.name
                        if hasattr(triggered_alarm.alarm, "info")
                        and triggered_alarm.alarm.info
                        else "N/A"
                    ),
                    "ALARM_KEY": (
                        triggered_alarm.alarm.info.key
                        if hasattr(triggered_alarm.alarm, "info")
                        and triggered_alarm.alarm.info
                        else "N/A"
                    ),
                    "ALARM_STATE": (
                        str(triggered_alarm.overallStatus)
                        if hasattr(triggered_alarm, "overallStatus")
                        else "N/A"
                    ),
                    "ALARM_TIME": current_time,
                    "VCENTER_IP": vcenter_ip,
                    "VCENTER_PORT": vcenter_port,
                }
                if hasattr(triggered_alarm, "entity") and triggered_alarm.entity:
                    entity = triggered_alarm.entity
                    alarm_data["ENTITY_NAME"] = (
                        entity.name if hasattr(entity, "name") else "N/A"
                    )
                    alarm_data["ENTITY_TYPE"] = (
                        type(entity).__name__ if entity else "N/A"
                    )
                else:
                    alarm_data["ENTITY_NAME"] = "N/A"
                    alarm_data["ENTITY_TYPE"] = "N/A"
                if (
                    hasattr(triggered_alarm.alarm, "info")
                    and triggered_alarm.alarm.info
                ):
                    alarm_info = triggered_alarm.alarm.info
                    alarm_data.update(
                        {
                            "ALARM_DESCRIPTION": (
                                alarm_info.description
                                if hasattr(alarm_info, "description")
                                else "N/A"
                            ),
                            "ALARM_ENABLED": (
                                alarm_info.enabled
                                if hasattr(alarm_info, "enabled")
                                else "N/A"
                            ),
                            "ALARM_SYSTEM_NAME": (
                                alarm_info.systemName
                                if hasattr(alarm_info, "systemName")
                                else "N/A"
                            ),
                            "ALARM_CREATION_EVENT_ID": (
                                alarm_info.creationEventId
                                if hasattr(alarm_info, "creationEventId")
                                else "N/A"
                            ),
                            "ALARM_LAST_MODIFIED_TIME": (
                                alarm_info.lastModifiedTime.isoformat()
                                if hasattr(alarm_info, "lastModifiedTime")
                                and alarm_info.lastModifiedTime
                                else "N/A"
                            ),
                            "ALARM_LAST_MODIFIED_USER": (
                                alarm_info.lastModifiedUser
                                if hasattr(alarm_info, "lastModifiedUser")
                                else "N/A"
                            ),
                        }
                    )
                alarms_info_list.append(alarm_data)
            except Exception as e:
                print(f"处理告警时出错: {str(e)}", file=sys.stderr)
                continue
        return alarms_info_list
    except Exception as e:
        print(f"获取vCenter告警信息失败: {str(e)}", file=sys.stderr)
        return []


def main():
    try:
        # 尝试使用更安全的协议
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        # 设置兼容旧系统的加密套件
        context.set_ciphers("DEFAULT@SECLEVEL=1")  # 降低安全级别以兼容旧系统
    except Exception as e:
        # print(f"创建SSL上下文时出错，使用备用方法: {str(e)}", file=sys.stderr)
        # 使用备用方法
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    try:
        # 连接vCenter
        service_instance = SmartConnect(
            host=vcenter_ip,
            user=username,
            pwd=password,
            port=vcenter_port,
            sslContext=context,
        )

        content = service_instance.RetrieveContent()

        # 将每个host信息依次发送到kafka
        hosts_info = get_hosts_info(content)
        for host in hosts_info:
            write_to_kafka(
                "宿主机" + host["HOST_NAME"],
                host,
                kafka_bootstrap_servers,
                kafka_host_topic,
            )
        write_to_file("hosts", hosts_info)
        print(f"成功获取并保存了 {len(hosts_info)} 个宿主机信息")

        # 将警报信息发送到kafka
        alarms_info = get_alarm_info(content)
        if alarms_info:
            for alarm in alarms_info:
                write_to_kafka(
                    "警报" + " " + alarm["ALARM_NAME"],
                    alarm,
                    kafka_bootstrap_servers,
                    kafka_alarm_topic,
                )
            write_to_file("alarms", alarms_info)
            print(f"成功获取并保存了 {len(alarms_info)} 个警报信息")

        # 断开连接
        Disconnect(service_instance)

    except Exception as e:
        print(f"连接错误: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    main()
