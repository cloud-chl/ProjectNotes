import getpass
from pyVim.connect import SmartConnect, Disconnect
import ssl
import sys
import warnings
import json
from datetime import datetime
import argparse


# 忽略 SSL 弃用警告
warnings.filterwarnings("ignore", category=DeprecationWarning)


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Standard Arguments for talking to vCenter"
    )
    parser.add_argument(
        "-U",
        "--url",
        type=str,
        required=True,
        action="store",
        help='VMWARE sdk whole url including protocol and port, like "https://192.168.11.70:443"',
    )
    parser.add_argument(
        "-u",
        "--user",
        required=True,
        action="store",
        help="User name to use when connecting to vCenter",
    )
    parser.add_argument(
        "-p",
        "--password",
        required=True,
        action="store",
        help="Password to use when connecting to vCenter",
    )
    parser.add_argument(
        "-S",
        "--disable_ssl_verification",
        required=False,
        action="store_true",
        help="Disable ssl host certificate verification",
    )
    return parser


def prompt_for_password(args):
    if not args.password:
        args.password = getpass.getpass(
            prompt=f"Enter password for host {args.host} and user {args.user}: "
        )

    return args


def get_args():
    parser = build_arg_parser()
    args = parser.parse_args()
    return prompt_for_password(args)


def urlSplittoIP(url):
    global ip
    ip = url.split(":")[1].split("//")[1]
    return ip


def urlSplittoPort(url):
    port = url.split(":")[2].split("/")[0]
    return port


def create_ssl_context():
    """创建兼容vCenter 6.5和7.0.3的SSL上下文"""
    try:
        # 优先尝试使用较新的协议版本
        context = ssl.SSLContext(ssl.PROTOCOL_TLS)
        context.options |= ssl.OP_NO_SSLv2
        context.options |= ssl.OP_NO_SSLv3

        # 设置密码套件兼容性
        try:
            # Python 3.10+ 支持设置密码套件
            context.set_ciphers("DEFAULT@SECLEVEL=1")
        except AttributeError:
            # 旧版Python使用默认密码套件
            pass

        # 禁用主机名验证和证书验证
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        return context

    except Exception as e:
        # print(f"创建SSL上下文时出错: {e}")
        # 回退到兼容性更好的设置
        return ssl._create_unverified_context()


def convert_vmodl_to_dict(obj):
    """递归将 pyVmomi 的 vmodl 对象转换为 Python 字典"""
    if hasattr(obj, "_type") and hasattr(obj, "value"):
        # 处理 ManagedObjectReference 对象
        return {"_ManagedObjectReference": {"type": obj._type, "value": obj.value}}

    elif hasattr(obj, "__dict__"):
        result = {}
        for key, value in obj.__dict__.items():
            if key.startswith("_") or value is None:
                continue  # 忽略私有属性和空值
            result[key] = convert_vmodl_to_dict(value)
        return result

    elif isinstance(obj, list):
        return [convert_vmodl_to_dict(item) for item in obj]

    else:
        return obj


def get_alarm_info(content):
    """获取vCenter中的已触发告警信息并转换为JSON字符串"""
    try:
        alarm_contents = content.rootFolder.triggeredAlarmState
        alarms_info_list = []

        for triggered_alarm in alarm_contents:
            try:
                alarm_state = triggered_alarm.alarm.info
                alarm_dict = convert_vmodl_to_dict(alarm_state)

                # 创建新的字典来避免类型问题
                new_alarm_dict = {}
                if isinstance(alarm_dict, dict):
                    new_alarm_dict.update(alarm_dict)

                # 安全地添加额外字段
                if hasattr(triggered_alarm, "entity"):
                    entity_obj = triggered_alarm.entity
                    new_alarm_dict["entity"] = str(entity_obj)
                    # 获取对象名称
                    try:
                        if hasattr(entity_obj, "name"):
                            new_alarm_dict["target_name"] = entity_obj.name
                        else:
                            new_alarm_dict["target_name"] = "未知"
                    except Exception as e:
                        new_alarm_dict["target_name"] = f"获取名称失败: {e}"
                if hasattr(triggered_alarm, "overallStatus"):
                    new_alarm_dict["triggeredState"] = str(
                        triggered_alarm.overallStatus
                    )
                if hasattr(triggered_alarm, "key"):
                    new_alarm_dict["key"] = str(triggered_alarm.key)
                new_alarm_dict["time"] = int(datetime.now().timestamp() * 1000)

                alarms_info_list.append(new_alarm_dict)
            except Exception as alarm_error:
                print(f"处理单个告警时出错: {alarm_error}")
                continue

        # 返回告警列表
        return alarms_info_list

    except Exception as e:
        print(f"获取vCenter告警信息失败: {str(e)}", file=sys.stderr)
        return []


def main():
    args = get_args()
    ip = urlSplittoIP(args.url)
    port = int(urlSplittoPort(args.url)) or 443
    context = create_ssl_context()

    try:
        service_instance = SmartConnect(
            host=ip, user=args.user, pwd=args.password, port=port, sslContext=context
        )

        content = service_instance.RetrieveContent()

        alarms_info = get_alarm_info(content)
        if alarms_info:
            # 逐条打印告警信息，每条告警占一行
            for alarm in alarms_info:
                # 创建告警信息的副本，移除key字段和其他可能包含UUID的字段
                alarm_copy = alarm.copy()
                # 移除可能包含UUID的字段
                fields_to_remove = ["key", "alarmKey"]
                for field in fields_to_remove:
                    if field in alarm_copy:
                        del alarm_copy[field]
                alarm_json = json.dumps(
                    alarm_copy, ensure_ascii=False, default=str, separators=(",", ":")
                )
                print(alarm_json)
        else:
            print("没有找到告警信息")
    except Exception as e:
        print(f"连接错误: {str(e)}", file=sys.stderr)
        return 1
    finally:
        try:
            if "service_instance" in locals() and service_instance:
                Disconnect(service_instance)
        except Exception:
            pass


if __name__ == "__main__":
    main()
