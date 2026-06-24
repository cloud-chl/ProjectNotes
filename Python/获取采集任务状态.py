# -*- coding: utf-8 -*-
import requests
import json
import datetime
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ========== 配置区 ==========
url = "https://ums.gf.com.cn"
# 账号
username = "wxcaihouliang"
# 密码（加密字符串）
password = "BA19bBEN5a+ym7MJxWsndnzpDVRYSuGW7Rjf+7xvrjnVNlBMMYToZhnu0pBzM+4e38Vgw0AzWFd2AEGiprYGEaM5WRLhSbNWNS1kxN+9ef9LpahSRO2+emJGvZe/Nnu8gRRNPchYWhUSPPzBTrfpzH+QJ1Lt2PxCDnGp+PsQJpU="
# 微信机器人
WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=2702dee9-a257-47aa-9b5d-785853b1c040"

# 任务状态映射（采集任务: 1.py/3, 流批任务: 0/1.py/2）
STATUS_LABEL = {1: "停止", 2: "异常", 3: "运行中", 6: "禁用"}
STREAM_STATUS_LABEL = {0: "停止", 1: "运行中", 2: "异常"}


def getToken():
    """登录 UMS 平台并获取后续接口调用所需的认证 token。"""
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


def getDataByConfig(token, api_path, fields_config, page_size, data_type_name, max_pages=None):
    """
    按字段配置分页拉取接口数据，并抽取脚本后续处理需要的字段。

    token: 认证 token。
    api_path: API 接口路径。
    fields_config: 字段配置字典，格式为 {"显示名称": "字段名"}，支持嵌套字段配置。
    page_size: 每页数据条数。
    data_type_name: 数据类型名称，用于日志输出和特殊分页处理。
    max_pages: 最多获取页数；为空时获取接口返回的全部分页。
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
                "condition": {
                    "startTime": "",
                    "endTime": "",
                    "flowId": 3
                },
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
                data = response_data.get("data")
                if data is None:
                    print(f"{data_type_name}返回 data 为空: {result.text[:200]}")
                    break
                records = data.get("records") or data.get("list") or []
                if not records:
                    # 可能是单个对象或分页 list 不同 key
                    if isinstance(data, list):
                        records = data
                    elif isinstance(data, dict) and not records:
                        print(f"{data_type_name}第 {page_num} 页返回结构未知: {list(data.keys())}")
                        break

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
                total_page = data.get("totalPage", 0)
                row_count = data.get("rowCount", 0)
                print(
                    f"{data_type_name}总页数: {total_page}, 总记录数: {row_count}, 已获取: {len(all_extracted_data)}"
                )

                if max_pages is not None and page_num >= max_pages:
                    print(f"{data_type_name}已获取完成，总计 {len(all_extracted_data)} 条")
                    break

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


def getCollectTask(token):
    """获取采集任务列表，并返回任务名称、目标、状态、异常信息等字段。"""
    api_path = "/snc-ng-server/task/findTaskPage"
    fields_config = {
        "任务名称": "taskName",
        "目标": "targetName",
        "状态": "status",
        "异常信息": "errorCause",
    }
    page_size = 20
    data_type_name = "采集任务"

    return getDataByConfig(token, api_path, fields_config, page_size, data_type_name)


def getStreamModule(token, tid):
    """根据流批任务 ID 查询模块节点详情，返回异常节点名称列表。"""
    api_url = url + "/snc-platform-manager/streamingWorkflow/getNodeLines"
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "accessToken": token,
        "snc-token": token,
    }
    try:
        resp = requests.post(api_url, json={"params": {"id": tid}}, headers=headers, verify=False)
        if resp.status_code != 200:
            return []
        data = resp.json().get("data", {})
        # 结构: data.nodes[].stepInfo.status, data.nodes[].label
        nodes = data.get("nodes", [])
        # 筛选异常节点：stepInfo 不为 None 且 status != 1.py（1.py=运行中）
        abnormal_nodes = []
        for node in nodes:
            step_info = node.get("stepInfo")
            if step_info is None:
                continue  # 跳过 Kafka 等无 stepInfo 的节点
            step_status = step_info.get("status")
            label = node.get("label", "未知节点")
            if step_status != 1:
                status_label = STATUS_LABEL.get(step_status, str(step_status))
                abnormal_nodes.append("{} ({})".format(label, status_label))
        return abnormal_nodes
    except Exception as e:
        print(f"  >>> 获取流批模块详情异常(id={tid}): {e}")
        return []


def getStreamTask(token):
    """获取流批任务列表，并返回任务名称、任务 ID、最后处理时间、状态等字段。"""
    api_path = "/snc-platform-manager/streamingWorkflow/pageList"
    fields_config = {
        "任务名称": "name",
        "任务ID": "id",
        "最后处理": "lastProcessTime",
        "状态": "status",
    }
    page_size = 50
    data_type_name = "流批任务"

    return getDataByConfig(token, api_path, fields_config, page_size, data_type_name)


def get_batch_workflow_status(token):
    """获取基线任务最近一次调度实例状态，用于判断离线加工任务是否异常。"""

    api_path = "/snc-platform-manager/batchWorkflowScheduleInstance/pageList"
    fields_config = {
        "任务名称": "batchWorkflowName",
        "任务ID": "batchWorkflowId",
        "最后处理": "endTime",
        "状态": "runningStatus",
    }
    page_size = 50
    max_pages = 1
    data_type_name = "基线任务"

    res = getDataByConfig(token, api_path, fields_config, page_size, data_type_name, max_pages)
    return res


def get_message_notifyhistory(token):
    """获取基线任务最近一次调度实例状态，用于判断离线加工任务是否异常。"""
    api_path = "/managerCenter/message/notifyHistory/page"
    fields_config = {
        "通知任务名称": "objectName",
        "通知内容": "objectContent",
        "业务系统": "strategyNames",
        "状态": "result",
        "发送时间": "sendTimeStr",
        "通知人": "userNames"
    }
    page_size = 50
    max_pages = 4
    data_type_name = "通知任务"

    res = getDataByConfig(token, api_path, fields_config, page_size, data_type_name, max_pages)
    return res


def send_wechat_alert(abnormal_tasks, task_type="通知任务", mention_users=None):
    """
    将异常任务列表组装为 markdown 内容，并发送到企业微信机器人。

    abnormal_tasks: 已筛选出的异常任务列表。
    task_type: 任务类型名称，用于告警标题和状态映射。
    mention_users: 需要提醒的企业微信用户 ID 列表，支持 @all。
    """
    if not abnormal_tasks:
        print(">>> 无异常任务，跳过告警")
        return

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    task_count = len(abnormal_tasks)
    total = min(task_count, 10)  # 单条消息最多展示 10 条

    # 构建 markdown 告警内容
    lines = [
        "## <font color=\"warning\">{}异常告警</font>".format(task_type),
    ]

    for i, task in enumerate(abnormal_tasks[:total], 1):
        name = task.get("任务名称") or task.get("通知任务名称") or "-"
        label_map = STATUS_LABEL if task_type == "采集任务" else STREAM_STATUS_LABEL
        status = label_map.get(task.get("状态"), str(task.get("状态", "-")))
        nodes = task.get("异常节点", [])
        target = task.get("目标", "-") or "-"

        lines.append("**{}**".format(name))
        lines.append(("> 检测时间: {}".format(now_str)))
        lines.append("> 任务状态：<font color=\"warning\">{}</font>".format(status))
        if task_type == "流批任务" and nodes:
            lines.append("> 异常节点：{}".format(", ".join(nodes)))
        elif task_type == "采集任务":
            lines.append("> 执行目标：{}".format(target))
            err = task.get("异常信息") or ""
            if err:
                lines.append("> 异常信息：<font color=\"warning\">{}</font>".format(err))
        elif task_type == "基线任务":
            exec_time = task.get("最后处理")
            exec_time_dt = datetime.datetime.strptime(exec_time, '%Y-%m-%d %H:%M:%S')
            now_dt = datetime.datetime.now()
            diff_seconds = (now_dt - exec_time_dt).total_seconds()
            diff_hours = diff_seconds / 3600
            lines.append(f"> 基线任务异常: 最后一次执行时间{exec_time_dt}, 与当前时间相差{diff_hours:.1f}小时")
        elif task_type == "通知任务":
            send_time = task.get("发送时间", "-") or "-"
            content = task.get("通知内容", "-") or "-"
            system_name = task.get("业务系统", "-") or "-"
            userNames = task.get("通知人", "-") or "-"
            lines.append("> 发送时间：{}".format(send_time))
            lines.append("> 业务系统：{}".format(system_name))
            lines.append("> 通知内容：{}".format(content))
            lines.append("> 通知人：{}".format(userNames))
        lines.append("")

    if task_count > 5:
        lines.append("> 共 **{}** 条异常，此处仅展示前 5 条".format(task_count))

    if mention_users:
        mention_text = ""
        for userid in mention_users:
            if userid == "@all":
                mention_text += "<@all>"
            else:
                mention_text += f"<@{userid}>"
        lines.append(f"\n{mention_text}")

    content = "\n".join(lines)

    payload = {
        "msgtype": "markdown",
        "markdown": {"content": content},
    }

    try:
        resp = requests.post(WEBHOOK, json=payload, timeout=10)
        if resp.status_code == 200 and resp.json().get("errcode") == 0:
            print(f">>> 告警已发送: {task_count} 条异常任务")
        else:
            print(f">>> 告警发送失败: {resp.text}")
    except requests.RequestException as e:
        print(f">>> 告警发送异常: {e}")


def main():
    token = getToken()
    if not token:
        print(">>> Token 获取失败，退出")
        exit(1)

    # ========== 采集任务 ==========
    print("\n=== 采集任务数据 ===")
    collect_tasks = getCollectTask(token)
    if collect_tasks is None:
        collect_tasks = []

    for t in collect_tasks:
        name = t.get("任务名称", "-")
        target = t.get("目标", "-")
        status = STATUS_LABEL.get(t.get("状态"), str(t.get("状态")))
        print(f"\n采集任务: {name}")
        print(f"执行目标: {target}")
        print(f"任务状态: {status}")

    # ========== 流批任务 ==========
    print("\n\n=== 流批任务数据 ===")
    stream_tasks = getStreamTask(token)
    if stream_tasks is None:
        stream_tasks = []

    for t in stream_tasks:
        name = t.get("任务名称", "-")
        last_time = t.get("最后处理", "-")
        status = STREAM_STATUS_LABEL.get(t.get("状态"), str(t.get("状态")))
        print(f"\n流批任务: {name}")
        print(f"最后处理: {last_time}")
        print(f"任务状态: {status}")

    # ========== 基线任务 ==========
    print("\n\n=== 基线任务数据 ===")
    baseline_task = get_batch_workflow_status(token)[0:1]
    if baseline_task is None:
        baseline_task = []

    name = baseline_task[0].get("任务名称", "-")
    last_time = baseline_task[0].get("最后处理", "-")
    status = 2 if datetime.datetime.now().timestamp() - datetime.datetime.strptime(last_time,'%Y-%m-%d %H:%M:%S').timestamp() > 4000 else baseline_task[0].get("状态", "-")
    print(f"\n流批任务: {name}")
    print(f"最后处理: {last_time}")
    print(f"任务状态: {status}")

    # ========== 通知任务 ==========
    print("\n\n=== 通知任务数据 ===")
    message_task = get_message_notifyhistory(token)
    if message_task is None:
        message_task = []

    for t in message_task:
        name = t.get("通知任务名称")
        content = t.get("通知内容")
        systemName = t.get("业务系统")
        status = t.get("状态")
        send_time = t.get("发送时间")
        userNames = t.get("通知人")
        print(f"\n通知任务: {name}")
        print(f"通知内容: {content}")
        print(f"业务系统: {systemName}")
        print(f"发送状态: {status}")
        print(f"发送时间: {send_time}")
        print(f"通知人: {userNames}")

    # ========== 采集任务汇总 ==========
    collect_abnormal = [t for t in collect_tasks if t.get("状态") == 2 or (t.get("状态") == 3 and t.get("异常信息"))]
    print(f"\n>>> 采集任务: {len(collect_tasks)} 条, 异常: {len(collect_abnormal)} 条")
    if collect_abnormal:
        for t in collect_abnormal:
            err = t.get("异常信息") or ""
            detail = t.get("目标", "-")
            if err:
                detail += " | error: " + err
            print(f"    [异常] {t.get('任务名称', '-')} -> {detail}")

    # ========== 流批任务汇总 ==========
    stream_abnormal = [t for t in stream_tasks if t.get("状态") == 2]
    print(f">>> 流批任务: {len(stream_tasks)} 条, 异常: {len(stream_abnormal)} 条")
    if stream_abnormal:
        for t in stream_abnormal:
            tid = t.get("任务ID")
            nodes = getStreamModule(token, tid) if tid else []
            t["异常节点"] = nodes
            node_str = ", ".join(nodes) if nodes else "无"
            print(f"    [异常] {t.get('任务名称', '-')} -> 异常节点: {node_str}")

    # ========== 离线加工任务汇总 ==========
    baseline_abnormal = [t for t in baseline_task if status == 2]
    print(f">>> 基线任务: {len(baseline_task)} 条, 异常: {len(baseline_abnormal)} 条")

    # ========== 通知任务汇总 ==========
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    message_abnormal = [t for t in message_task if
                        t.get("状态") == "未发送" and (t.get("发送时间") or "").startswith(today_str)]
    print(f">>> 通知任务: {len(message_task)} 条, 异常: {len(message_abnormal)} 条")

    # 发送告警
    send_wechat_alert(collect_abnormal, "采集任务")
    send_wechat_alert(stream_abnormal, "流批任务")
    send_wechat_alert(baseline_abnormal, "基线任务")
    send_wechat_alert(message_abnormal, "通知任务")


if __name__ == "__main__":
    main()
