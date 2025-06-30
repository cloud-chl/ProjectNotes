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
CURRENT_TIME = datetime.datetime.now().strftime("%Y%m")
ES_URL = "http://192.168.1.1:9200"
ES_INDEX = "index_name_" + CURRENT_TIME
ES_USER = "elastic"
ES_PASS = "elastic@123"


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
    api_path = "/v1/api/"
    fields_config = {
        "任务ID": "id",
        "任务名称": "name",
        "状态": "status",
        "任务等级": "level",
        "异常信息": "errCause",
    }
    page_size = 50
    data_type_name = "API数据"

    return getDataByConfig(token, api_path, fields_config, page_size, data_type_name)


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
        if typeName == "API任务" and status_int != 1:
            is_abnormal = True

        if is_abnormal:
            # 异常状态，写入新记录
            alarm_data = {
                "firstAlarm": True,
                "firstAlarmTime": timestamp,
                "alarmId": alarm_id,
                "alarmName": f"{taskId}_{taskName}_{typeName} 采集异常，异常信息：{taskContent}",
                "alarmContent": f"{taskId}_{taskName}_{typeName} 采集异常，异常信息：{taskContent}",
                "status": 1,
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
                print(f"ES记录不存在，无需更新: {alarm_id}")
            else:
                print(f"更新ES失败: {update_response.text}")
                return False

        return True

    except Exception as e:
        print(f"写入ES异常: {e}")
        return False


if __name__ == "__main__":

    # 获取Token
    token = getToken()
    # print(f"获取到的Token: {token}")

    # 获取API数据
    print("\n=== API数据 ===")
    stream_data = getStreamTaskData(token)
    if stream_data:
        for record in stream_data:
            task_id = record.get("任务ID", "")
            task_name = record.get("任务名称", "")
            task_status = record.get("任务状态", "")
            task_errcause = record.get("异常信息", "")
            write_to_es(task_id, task_name, task_status, "API任务", task_errcause)
    else:
        print("数据获取失败")
