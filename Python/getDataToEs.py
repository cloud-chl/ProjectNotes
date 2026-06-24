# -*- coding: utf-8 -*-
import requests
from requests.auth import HTTPBasicAuth
import json
import datetime
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 平台连接信息
url = "http://192.168.1.1:8080"
username = "admin"
password = "admin@123"

# ES连接信息
CURRENT_MONTH = datetime.datetime.now().strftime("%Y%m")
# ES_URL = "http://192.168.33.225:9200"
ES_URL = "https://es-cn-s114ar5vh0007f22o.elasticsearch.aliyuncs.com:9200"
ES_INDEX = "alarms_" + CURRENT_MONTH
ES_USER = "elastic"
ES_PASS = "Elastic#9200"


# 获取Token
def getToken():
    # 登录接口
    loginUrl = url + "/user/passport/loginCode"

    # 请求参数
    dataString = {"params": {"account": username, "password": password}}

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    }
    try:
        result = requests.post(
            url=loginUrl, json=dataString, headers=headers, verify=False
        )
    except Exception as e:
        print("getToken http requests failed: {0}".format(e))
        return False
    json_text = json.loads(result.text)
    if result.status_code == 200 and json_text["msgCode"] == 200:
        # print(json_text['data']['certification']['token'])
        token = json_text["data"]["certification"]["token"]
        return token
    elif result.status_code == 200 and json_text["msgCode"] == 406:
        print(
            "Get token failed, http code: % s, % s"
            % (str(json_text["msgCode"]), json_text["message"])
        )
        exit(1)
    else:
        print(
            "Get token failed, http code: % s, % s"
            % (str(result.status_code), result.text)
        )
        exit(1)


# 通用数据获取方法
def getDataByConfig(token, api_path, fields_config, page_size, data_type_name):
    """
    通用数据获取方法
    token: 认证token
    api_path: API接口路径
    fields_config: 字段配置字典，格式为 {"显示名称": "字段名"}
    page_size: 每页数据条数
    data_type_name: 数据类型名称（用于日志显示）
    """

    # 构建请求URL
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
        # 请求体数据
        request_data = {
            "params": {
                "condition": {},
                "pagination": {
                    "pagenum": page_num,
                    "pagesize": page_size,
                    "sort": None,
                },
            }
        }

        try:
            result = requests.post(
                url=api_url, json=request_data, headers=headers, verify=False
            )
            print(
                f"正在获取{data_type_name}第 {page_num} 页，状态码: {result.status_code}"
            )

            if result.status_code == 200:
                response_data = json.loads(result.text)
                records = response_data["data"]["records"]

                # 检查是否还有数据
                if not records:
                    print(f"{data_type_name}第 {page_num} 页没有数据，获取完成")
                    break

                # 提取指定字段
                for record in records:
                    extracted_record = {}
                    for field_name, field_config in fields_config.items():
                        if isinstance(field_config, dict):
                            # 处理嵌套字段
                            extracted_record[field_name] = {}

                            # 检查是否有父字段配置
                            parent_field_name = field_config.get(
                                "_parent_field", field_name
                            )
                            is_json_field = field_config.get("_is_json", False)

                            # 获取父对象
                            parent_object = record.get(parent_field_name, {})

                            # 如果是JSON字符串字段，先解析
                            if is_json_field and isinstance(parent_object, str):
                                try:
                                    parent_object = json.loads(parent_object)
                                except json.JSONDecodeError:
                                    parent_object = {}

                            for sub_name, sub_config in field_config.items():
                                if sub_name in ["_parent_field", "_is_json"]:
                                    continue  # 跳过特殊配置

                                if isinstance(sub_config, str):
                                    # 处理点号分隔的嵌套路径
                                    if "." in sub_config:
                                        # 例如 "param.clusterName"
                                        value = parent_object
                                        for key in sub_config.split("."):
                                            if isinstance(value, dict):
                                                value = value.get(key, "")
                                            else:
                                                value = ""
                                                break
                                        extracted_record[field_name][sub_name] = value
                                    else:
                                        # 普通字段
                                        if isinstance(parent_object, dict):
                                            extracted_record[field_name][sub_name] = (
                                                parent_object.get(sub_config, "")
                                            )
                                        else:
                                            extracted_record[field_name][sub_name] = ""
                                else:
                                    # 处理更深层嵌套
                                    extracted_record[field_name][sub_name] = record.get(
                                        sub_config, ""
                                    )
                        else:
                            # 处理普通字段
                            extracted_record[field_name] = record.get(field_config, "")

                    all_extracted_data.append(extracted_record)

                print(f"{data_type_name}第 {page_num} 页获取到 {len(records)} 条记录")

                # 检查是否还有更多页
                total_page = response_data["data"].get("totalPage", 0)
                row_count = response_data["data"].get("rowCount", 0)
                print(
                    f"{data_type_name}总页数: {total_page}, 总记录数: {row_count}, 已获取: {len(all_extracted_data)}"
                )

                if page_num >= total_page or len(all_extracted_data) >= row_count:
                    print(
                        f"{data_type_name}已获取完成，总计 {len(all_extracted_data)} 条"
                    )
                    break

                page_num += 1
            else:
                print(
                    f"获取{data_type_name}第 {page_num} 页失败，状态码: {result.status_code}"
                )
                break

        except Exception as e:
            print(f"获取{data_type_name}第 {page_num} 页异常: {e}")
            break

    print(f"{data_type_name}总共获取到 {len(all_extracted_data)} 条记录")
    return all_extracted_data


# 获取流批数据
def getStreamTaskData(token):
    api_path = "/api/v1/listpage"
    fields_config = {
        "任务ID": "id",
        "任务名称": "name",
        "状态": "status",
        "重要等级": "level",
        "启动时间": "startTime",
        "最新数据": "lastProcessTime",
        "更新用户": "updateUserName",
        "更新时间": "updateTime",
        "备注": "description",
    }
    page_size = 50
    data_type_name = "流批数据"

    return getDataByConfig(token, api_path, fields_config, page_size, data_type_name)


# 写入文件函数
def write_to_file(content, filename=None):
    if filename is None:
        # 生成带时间戳的文件名
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"流批数据_{timestamp}.json"

    try:
        with open(filename, "w", encoding="utf-8") as f:
            if isinstance(content, str):
                f.write(content)
            else:
                json.dump(content, f, ensure_ascii=False, indent=2)
        print(f"数据已保存到文件: {filename}")
        return filename
    except Exception as e:
        print(f"写入文件失败: {e}")
        return None


def write_to_es(taskId, taskName, taskStatus, typeName, taskContent):
    try:
        # 使用毫秒时间戳
        timestamp = int(datetime.datetime.now().timestamp() * 1000)

        # 构造alarmId（用于查询和更新）
        alarm_id = f"{taskId}_{taskName}_{typeName}"

        # 检查status值
        status_int = int(taskStatus) if taskStatus and str(taskStatus).isdigit() else 0

        # 判断是否为异常状态
        is_abnormal = False
        if typeName == "api接口数据采集任务" and status_int == 2:
            is_abnormal = True

        if is_abnormal:
            # 异常状态，先查询ES中是否存在该alarmId的记录
            query_url = f"{ES_URL}/{ES_INDEX}/_doc/{alarm_id}"

            try:
                query_response = requests.get(
                    query_url,
                    auth=HTTPBasicAuth(ES_USER, ES_PASS),
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )

                if query_response.status_code == 200:
                    # 记录存在，更新字段
                    existing_data = query_response.json()
                    source_data = existing_data.get("_source", {})

                    # 更新字段
                    update_data = {
                        "doc": {
                            "firstAlarm": False,  # 不是首次告警
                            "status": 1,  # 告警状态
                            "alarmTime": timestamp,  # 更新告警时间
                        }
                    }

                    # 构造_update请求URL
                    update_url = f"{ES_URL}/{ES_INDEX}/_update/{alarm_id}"

                    update_response = requests.post(
                        update_url,
                        auth=HTTPBasicAuth(ES_USER, ES_PASS),
                        headers={"Content-Type": "application/json"},
                        data=json.dumps(update_data),
                        timeout=30,
                    )

                    print(f"更新ES状态码: {update_response.status_code}")
                    if update_response.status_code == 200:
                        print(f"成功更新ES告警记录: {alarm_id}")
                    else:
                        print(f"更新ES失败: {update_response.text}")
                        return False

                elif query_response.status_code == 404:
                    # 记录不存在，插入新记录
                    alarm_data = {
                        "firstAlarm": True,
                        "firstAlarmTime": timestamp,
                        "alarmId": alarm_id,
                        "globalAlarmId": alarm_id,
                        "alarmName": f"{typeName} 异常, 任务名称:{taskName}, 异常信息：{taskContent}",
                        "alarmContent": f"{typeName} 异常, 任务名称:{taskName}, 异常信息：{taskContent}",
                        "priorityId": 3,
                        "priorityName": "一般",
                        "alarmTime": timestamp,
                        "status": 1,
                        "resourceName": "统一登录平台",
                        "metricName": "service_monitor",
                        "metricCode": "service_monitor",
                        "value": "0",
                        "count": 1,
                    }

                    # 构造请求URL - 使用alarmId作为文档ID
                    url = f"{ES_URL}/{ES_INDEX}/_doc/{alarm_id}"

                    # 发送POST请求写入数据
                    response = requests.post(
                        url,
                        auth=HTTPBasicAuth(ES_USER, ES_PASS),
                        headers={"Content-Type": "application/json"},
                        data=json.dumps(alarm_data),
                        timeout=30,
                    )

                    # 输出结果
                    print(f"写入ES状态码: {response.status_code}")
                    if response.status_code == 201:
                        print(f"成功写入ES告警: {alarm_id}")
                    else:
                        print(f"写入ES失败: {response.text}")
                        return False
                else:
                    print(f"查询ES记录失败, 状态码: {query_response.status_code}")
                    return False

            except Exception as e:
                print(f"查询ES记录异常: {e}")
                return False

        else:
            # 正常状态，更新现有记录（如果存在）
            update_data = {
                "doc": {
                    "status": 0,
                    "recoverTime": timestamp,
                }
            }

            # 构造_update请求URL
            update_url = f"{ES_URL}/{ES_INDEX}/_update/{alarm_id}"

            update_response = requests.post(
                update_url,
                auth=HTTPBasicAuth(ES_USER, ES_PASS),
                headers={"Content-Type": "application/json"},
                data=json.dumps(update_data),
                timeout=30,
            )

            print(f"更新ES状态码: {update_response.status_code}")
            if update_response.status_code == 200:
                print(f"成功更新ES记录: {alarm_id}")
            elif update_response.status_code == 404:
                print(f"ES记录不存在, 无需更新: {alarm_id}")
            else:
                print(f"更新ES失败: {update_response.text}")
                return False

        return True

    except Exception as e:
        print(f"写入ES异常: {e}")
        return False


if __name__ == "__main__":
    # 生成时间戳
    # timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    # 获取Token
    token = getToken()
    # print(f"获取到的Token: {token}")

    # 获取流批数据
    print("\n=== 采集数据 ===")
    stream_data = getStreamTaskData(token)
    if stream_data:
        # stream_filename = f"流批数据_{timestamp}.json"
        # write_to_file(stream_data, stream_filename)
        for record in stream_data:
            task_id = record.get("任务ID", "")
            task_name = record.get("流程名称", "")
            task_status = record.get("状态", "")
            write_to_es(task_id, task_name, task_status, "采集任务", "null")
    else:
        print("api数据获取失败")
