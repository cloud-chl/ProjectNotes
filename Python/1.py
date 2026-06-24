# -*- coding: utf-8 -*-
import requests
import json
import datetime
import urllib3
from kafka import KafkaProducer

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 平台连接信息
url = "http://192.168.33.223:8080"
username = "admin"
password = "V8l5cDoJLPFhTJpSmwRGUbH0+0LZiyJgQrfJYInP/59Frs7ZiabQQHYyRgSbA1n8JvxwpMAow7oqonZh9ZkWoolP4fPD82e6rXguBDMb/phpTzxbb9cMbq9svEMWCGA/OcU775g8HkmTwsbf9y91ASTTHCqFCShwBYUP0Ctmrfo="

# Kafka 连接信息
KAFKA_BROKERS = ["192.168.33.225:9092"]
KAFKA_TOPIC = "webhook_alarm"

# 告警默认值
APP_NAME = " 统一监控分析平台"
PRIORITY = 3  # 告警等级: 1=紧急 2=严重 3=一般
RESOURCE_NAME = " 统一监控分析平台"
METRIC_NAME = "service_monitor"
METRIC_CODE = "service_monitor"

# 任务状态映射
STATUS_LABEL = {0: "停止", 1: "运行中", 2: "异常", 3: "等待中"}


def getToken():
    loginUrl = url + "/user/passport/loginCode"
    dataString = {"params": {"account": username, "password": password}}
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    }
    try:
        result = requests.post(url=loginUrl, json=dataString, headers=headers, verify=False)
    except Exception as e:
        print("getToken http requests failed: {0}".format(e))
        return False
    json_text = json.loads(result.text)
    if result.status_code == 200 and json_text["msgCode"] == 200:
        return json_text["data"]["certification"]["token"]
    elif result.status_code == 200 and json_text["msgCode"] == 406:
        print("Get token failed, http code: % s, % s" % (str(json_text["msgCode"]), json_text["message"]))
        exit(1)
    else:
        print("Get token failed, http code: % s, % s" % (str(result.status_code), result.text))
        exit(1)


def getDataByConfig(token, api_path, fields_config, page_size, data_type_name):
    api_url = url + api_path
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Authorization": "admin",
        "Connection": "keep-alive",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": f"{url}",
        "Referer": f"{url}{api_path}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        "accessToken": f"{token}",
        "snc-token": f"{token}",
    }
    all_extracted_data = []
    page_num = 1
    while True:
        request_data = {
            "params": {
                "condition": {},
                "pagination": {"pagenum": page_num, "pagesize": page_size, "sort": None},
            }
        }
        try:
            result = requests.post(url=api_url, json=request_data, headers=headers, verify=False)
            print(f"正在获取{data_type_name}第 {page_num} 页，状态码: {result.status_code}")
            if result.status_code == 200:
                response_data = json.loads(result.text)
                records = response_data["data"]["records"]
                if not records:
                    print(f"{data_type_name}第 {page_num} 页没有数据，获取完成")
                    break
                for record in records:
                    extracted_record = {}
                    for field_name, field_config in fields_config.items():
                        if isinstance(field_config, dict):
                            extracted_record[field_name] = {}
                            parent_field_name = field_config.get("_parent_field", field_name)
                            is_json_field = field_config.get("_is_json", False)
                            parent_object = record.get(parent_field_name, {})
                            if is_json_field and isinstance(parent_object, str):
                                try:
                                    parent_object = json.loads(parent_object)
                                except json.JSONDecodeError:
                                    parent_object = {}
                            for sub_name, sub_config in field_config.items():
                                if sub_name in ["_parent_field", "_is_json"]:
                                    continue
                                if isinstance(sub_config, str):
                                    if "." in sub_config:
                                        value = parent_object
                                        for key in sub_config.split("."):
                                            if isinstance(value, dict):
                                                value = value.get(key, "")
                                            else:
                                                value = ""
                                                break
                                        extracted_record[field_name][sub_name] = value
                                    else:
                                        if isinstance(parent_object, dict):
                                            extracted_record[field_name][sub_name] = parent_object.get(sub_config, "")
                                        else:
                                            extracted_record[field_name][sub_name] = ""
                                else:
                                    extracted_record[field_name][sub_name] = record.get(sub_config, "")
                        else:
                            extracted_record[field_name] = record.get(field_config, "")
                    all_extracted_data.append(extracted_record)
                print(f"{data_type_name}第 {page_num} 页获取到 {len(records)} 条记录")
                total_page = response_data["data"].get("totalPage", 0)
                row_count = response_data["data"].get("rowCount", 0)
                print(f"{data_type_name}总页数: {total_page}, 总记录数: {row_count}, 已获取: {len(all_extracted_data)}")
                if page_num >= total_page or len(all_extracted_data) >= row_count:
                    print(f"{data_type_name}已获取完成，总计 {len(all_extracted_data)} 条")
                    break
                page_num += 1
            else:
                print(f"获取{data_type_name}第 {page_num} 页失败，状态码: {result.status_code}")
                break
        except Exception as e:
            print(f"获取{data_type_name}第 {page_num} 页异常: {e}")
            break
    print(f"{data_type_name}总共获取到 {len(all_extracted_data)} 条记录")
    return all_extracted_data


def getStreamTaskData(token):
    api_path = "/snc-platform-manager/streamingWorkflow/pageList"
    fields_config = {
        "任务ID": "id",
        "流程名称": "name",
        "状态": "status",
        "重要等级": "level",
        "CPU核心数": "totalVCores",
        "内存": "totalMemory",
        "融合节点": "fusionStep",
        "启动时间": "startTime",
        "最新数据": "lastProcessTime",
        "模块信息": "moduleTasks",
        "更新用户": "updateUserName",
        "更新时间": "updateTime",
        "Flink运行环境": "flinkRuntimeEnvName",
        "备注": "description",
    }
    page_size = 50
    data_type_name = "流批数据"
    return getDataByConfig(token, api_path, fields_config, page_size, data_type_name)


def getCollectTaskData(token):
    api_path = "/snc-ng-server/task/findTaskPage"
    fields_config = {
        "任务ID": "id",
        "任务名称": "taskName",
        "任务状态": "status",
        "异常信息": "errorCause",
        "Proxy集群": "clusterName",
        "执行代理": "executeTarget",
        "执行对象": "clusterName",
        "最后执行时间": "latestReportTime",
        "定时周期": "scheduleCron",
        "输出Topic": {
            "_parent_field": "resultReturnProtocol",
            "_is_json": True,
            "协议类型": "protocol",
            "集群名称": "param.clusterName",
            "Topic": "param.topic",
        },
        "更新时间": "updateTime",
    }
    page_size = 20
    data_type_name = "采集任务数据"
    return getDataByConfig(token, api_path, fields_config, page_size, data_type_name)


def getDiscoveryTaskData(token):
    api_path = "/snc-cmdb-discovery/discovery/task/getTasklist"
    fields_config = {
        "任务ID": "id",
        "任务名称": "taskName",
        "任务状态": "regularStatus",
        "任务类型": "taskType",
        "扫描范围": "remark",
        "定时周期": "regularDesc",
        "最后执行时间": "lastExcuteTime",
        "最后执行结果": "lastExcuteMessage",
        "状态": "regularStatus",
    }
    page_size = 50
    data_type_name = "自发现数据"
    return getDataByConfig(token, api_path, fields_config, page_size, data_type_name)


def build_alarm(task, type_name, alarm_status=1):
    """
    根据任务数据构建 Kafka 告警消息，字段对照 webhook 告警接入文档。
    必填: alarmId/triggerId, alarmName, alarmContent, alarmTime, appName, metricName,
           priority, resourceName, status, value
    非必填: cmdbId, metricCode, recoverTime(status=0时必填), tags, unit
    """
    task_id = str(task.get("任务ID", ""))
    task_name = task.get("流程名称") or task.get("任务名称", "") or "未知任务"
    task_status = task.get("状态") or task.get("任务状态", "")
    task_content = task.get("异常信息") or task.get("最后执行结果", "")

    if type_name == "流批任务":
        alarm_name = "{} 采集异常".format(task_name)
        alarm_content = "流批任务[{}] 状态异常, 请及时处理".format(task_name)
        alarm_value = str(task_status)
    elif type_name == "采集任务":
        alarm_name = "{} 采集异常".format(task_name)
        alarm_content = "采集任务[{}] 状态异常, 异常信息: {}".format(task_name, task_content or "无")
        alarm_value = str(task_status)
    else:
        alarm_name = "{} 发现异常".format(task_name)
        alarm_content = "自发现任务[{}] 状态异常, 最后执行结果: {}".format(task_name, task_content or "无")
        alarm_value = str(task_status)

    now_ms = int(datetime.datetime.now().timestamp() * 1000)

    return {
        "alarmId": "{}_{}_{}".format(task_id, task_name, type_name),
        "triggerId": "{}_{}_{}".format(task_id, task_name, type_name),
        "alarmName": alarm_name,
        "alarmContent": alarm_content,
        "alarmTime": now_ms,
        "appName": APP_NAME,
        "cmdbId": "",
        "metricCode": METRIC_CODE,
        "metricName": METRIC_NAME,
        "priority": PRIORITY,
        "recoverTime": now_ms if alarm_status == 0 else 0,
        "resourceName": RESOURCE_NAME,
        "status": alarm_status,
        "tags": {
            "taskId": task_id,
            "taskName": task_name,
            "taskStatus": str(task_status),
            "typeName": type_name,
        },
        "unit": "",
        "value": alarm_value,
    }


def send_to_kafka(messages, topic=None):
    """推送告警数据到 Kafka"""
    if topic is None:
        topic = KAFKA_TOPIC
    if not messages:
        print(">>> 无数据需推送 Kafka")
        return True
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_BROKERS,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        )
        for msg in messages:
            producer.send(topic, value=msg)
        producer.flush()
        producer.close()
        print(">>> Kafka 推送成功, topic: {}, 共 {} 条".format(topic, len(messages)))
        return True
    except Exception as e:
        print(">>> Kafka 推送失败: {}".format(e))
        return False


if __name__ == "__main__":
    token = getToken()
    if not token:
        print(">>> Token 获取失败，退出")
        exit(1)

    all_alarms = []

    # ========== 流批任务 ==========
    print("\n=== 流批数据 ===")
    stream_data = getStreamTaskData(token)
    if stream_data:
        for record in stream_data:
            task_status = record.get("状态", "")
            status_int = int(task_status) if task_status and str(task_status).isdigit() else 0
            if status_int:  # 非运行中即异常
            # if status_int != 1:  # 非运行中即异常
                all_alarms.append(build_alarm(record, "流批任务", alarm_status=1))
    else:
        print("流批数据获取失败")

    # ========== 采集任务 ==========
    print("\n=== 采集任务数据 ===")
    collect_data = getCollectTaskData(token)
    if collect_data:
        for record in collect_data:
            task_status = record.get("任务状态", "")
            status_int = int(task_status) if task_status and str(task_status).isdigit() else 0
            if status_int:  # 非运行中即异常
            # if status_int != 3:  # 非运行中即异常
                all_alarms.append(build_alarm(record, "采集任务", alarm_status=1))
    else:
        print("采集任务数据获取失败")

    # ========== 自发现任务 ==========
    print("\n=== 自发现数据 ===")
    discovery_data = getDiscoveryTaskData(token)
    if discovery_data:
        for record in discovery_data:
            task_status = record.get("任务状态", "")
            task_content = record.get("最后执行结果", "")
            status_int = int(task_status) if task_status and str(task_status).isdigit() else 0
            if status_int:
            # if status_int != 1 or task_content:
                all_alarms.append(build_alarm(record, "自发现任务", alarm_status=1))
    else:
        print("自发现数据获取失败")

    # ========== 推送 Kafka ==========
    print("\n>>> 共检测到 {} 条异常, 推送Kafka...".format(len(all_alarms)))
    send_to_kafka(all_alarms)
    print(">>> 巡检完毕")
