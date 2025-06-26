import requests
import json
import datetime

url = "http://192.168.1.1:8080"
# 账号
user = ""
# 密码（加密字符串）
password = ""


# 获取Token
def getToken():
    # 登录接口
    loginUrl = url + "/api/v1/login"

    # 请求参数
    dataString = {"params": {"account": user, "password": password}}

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
        token = json_text["data"]["token"]
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
        "Token": f"{token}",
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
    api_path = "/api/v1/login/pageList"
    fields_config = {"任务名称": "name", "状态": "status", "重要等级": "level"}
    page_size = 20
    data_type_name = "api数据"

    return getDataByConfig(token, api_path, fields_config, page_size, data_type_name)


# 写入文件函数
def write_to_file(content, filename=None):
    if filename is None:
        # 生成带时间戳的文件名
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"api数据_{timestamp}.json"

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


if __name__ == "__main__":
    # 生成时间戳
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    # 获取Token
    token = getToken()
    # print(f"获取到的Token: {token}")

    # # 获取流批数据
    # print("\n=== api数据 ===")
    stream_data = getStreamTaskData(token)
    if stream_data:
        stream_filename = f"api数据_{timestamp}.json"
        write_to_file(stream_data, stream_filename)
        # print(json.dumps(stream_data, indent=2, ensure_ascii=False))
    else:
        print("api数据获取失败")
