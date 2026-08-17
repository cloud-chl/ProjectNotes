# -*- coding: utf-8 -*-
import requests
import json
import datetime
import time
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

# ========== 目标集群 & 慢SQL看板配置 ==========
TARGET_CLUSTER_NAME = "统一监控系统_15067_4003"
# 慢SQL看板模板ID（从浏览器 F12 抓包获取）
SLOW_SQL_CUSTOM_ID = "2042539981649481730"
# 查询时间窗口（分钟），默认拉取最近 30 分钟
QUERY_WINDOW_MINUTES = 30


def getToken():
    """登录 UMS 平台并获取后续接口调用所需的认证 token。"""
    loginUrl = url + "/user/passport/loginCode"

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


def getClusterCmdbId(token):
    """
    从 monitorOverview 接口分页查找目标集群的 cmdbId。

    token: 认证 token。
    返回目标集群的 cmdbId，找不到则返回 None。
    """
    api_path = "/snc-telemetry-apm/monitor/monitorOverview"
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

    page_num = 1

    while True:
        request_data = {
            "params": {
                "condition": {
                    "alarmPriority": [],
                    "keyword": "",
                    "monitorType": "database",
                    "resourceCodes": ["tdsql_mysql"],
                    "instanceCode": "cluster",
                    "treeType": "resource",
                    "relationCmdbId": None,
                },
                "pagination": {
                    "pagenum": page_num,
                    "pagesize": 10,
                    "sort": {"name": "", "type": ""},
                    "sorting": "",
                    "sorts": [{"name": "", "type": ""}],
                },
            }
        }

        try:
            result = requests.post(
                url=api_url, json=request_data, headers=headers, verify=False
            )
            print(f"正在查找集群第 {page_num} 页，状态码: {result.status_code}")

            if result.status_code == 200:
                response_data = json.loads(result.text)
                data = response_data.get("data")
                if data is None:
                    print(f"返回 data 为空: {result.text[:200]}")
                    break

                records = data.get("records", [])
                if not records:
                    print(f"第 {page_num} 页没有数据")
                    break

                print(f"第 {page_num} 页获取到 {len(records)} 条集群")

                for r in records:
                    if r.get("instanceName") == TARGET_CLUSTER_NAME:
                        cmdb_id = r.get("cmdbId")
                        print(f">>> 找到目标集群「{TARGET_CLUSTER_NAME}」, cmdbId = {cmdb_id}")
                        return cmdb_id

                total_page = data.get("totalPage", 0)
                print(f"总页数: {total_page}")
                if page_num >= total_page:
                    print(f"已遍历全部 {total_page} 页，未找到目标集群「{TARGET_CLUSTER_NAME}」")
                    break

                page_num += 1
            else:
                print(f"请求失败，状态码: {result.status_code}, 响应: {result.text[:200]}")
                break

        except Exception as e:
            print(f"请求异常: {e}")
            break

    return None


def getSlowSQLDetail(token, cmdb_id, page_size=20):
    """
    根据集群 cmdbId 获取慢 SQL 详细列表。

    token: 认证 token。
    cmdb_id: 目标集群的 cmdbId。
    page_size: 每页数据条数。
    """
    api_path = "/snc-telemetry-apm/dashboard/getDashboardData"
    api_url = url + api_path

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Authorization": "admin",
        "Connection": "keep-alive",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": f"{url}",
        "Referer": f"{url}/snc-telemetry-apm/monitor/monitorOverview",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        "accessToken": f"{token}",
        "snc-token": f"{token}",
    }

    # 时间窗口：当前时间往前推 QUERY_WINDOW_MINUTES 分钟
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - QUERY_WINDOW_MINUTES * 60 * 1000

    all_records = []
    page_num = 1

    while True:
        request_data = {
            "params": {
                "customId": SLOW_SQL_CUSTOM_ID,
                "cmdbId": cmdb_id,
                "queryTimes": [start_ms, now_ms],
                "hasEdit": False,
                "filterSelfDiscoveryMetric": [],
                "pagination": {
                    "pagenum": page_num,
                    "pagesize": page_size,
                },
            }
        }

        try:
            result = requests.post(
                url=api_url, json=request_data, headers=headers, verify=False
            )
            print(f"正在获取慢SQL详情第 {page_num} 页，状态码: {result.status_code}")

            if result.status_code == 200:
                response_data = json.loads(result.text)
                data = response_data.get("data")
                if data is None:
                    print(f"返回 data 为空: {result.text[:200]}")
                    break

                form_data = data.get("formData", {})
                records = form_data.get("rows", [])
                columns = form_data.get("columns", [])

                if not records:
                    print(f"第 {page_num} 页没有数据，获取完成")
                    break

                # 解析每行数据：字段值包裹在 {singleData: 实际值} 中
                parsed_records = []
                for row in records:
                    parsed = {}
                    for col in columns:
                        col_key = col.get("key", "")
                        cell = row.get(col_key)
                        if isinstance(cell, dict):
                            parsed[col_key] = cell.get("singleData", cell)
                        else:
                            parsed[col_key] = cell
                    parsed_records.append(parsed)

                all_records.extend(parsed_records)
                print(f"第 {page_num} 页获取到 {len(records)} 条慢SQL")

                # 检查分页：可能返回 totalPage / rowCount，也可能在 data 顶层
                total_page = data.get("totalPage", 0) or form_data.get("totalPage", 0)
                row_count = data.get("rowCount", 0) or form_data.get("rowCount", 0)

                if total_page > 0 and page_num >= total_page:
                    print(f"慢SQL详情已获取完成，总计 {len(all_records)} 条")
                    break

                if len(records) < page_size:
                    # 不足一页说明已经拉完
                    print(f"慢SQL详情已获取完成，总计 {len(all_records)} 条")
                    break

                page_num += 1
            else:
                print(
                    f"获取慢SQL详情失败，状态码: {result.status_code}, "
                    f"响应: {result.text[:200]}"
                )
                break

        except Exception as e:
            print(f"获取慢SQL详情异常: {e}")
            break

    return all_records


def print_slow_sql_list(records):
    """打印慢 SQL 详细列表。"""
    if not records:
        print(">>> 无慢SQL记录")
        return

    print(f"\n{'='*90}")
    print(f"慢SQL详情列表（共 {len(records)} 条）")
    print(f"{'='*90}")

    for i, r in enumerate(records, 1):
        print(f"\n--- 第 {i} 条 ---")
        print(f"  ID:           {r.get('id', '-')}")
        print(f"  SQL:\n{r.get('example_sql', '-')}")
        print(f"  指纹:         {r.get('fingerprint', '-')}")
        print(f"  查询次数:     {r.get('query_count', '-')}")
        print(f"  平均耗时:     {r.get('query_time_avg', '-')}s")
        print(f"  最大耗时:     {r.get('query_time_max', '-')}s")
        print(f"  中位耗时:     {r.get('query_time_median', '-')}s")
        print(f"  总耗时:       {r.get('query_time_sum', '-')}s")
        print(f"  平均锁等待:   {r.get('lock_time_avg', '-')}s")
        print(f"  扫描行数:     {r.get('rows_examined_sum', '-')}")
        print(f"  返回行数:     {r.get('rows_sent_sum', '-')}")
        print(f"  数据库:       {r.get('db', '-')}")
        print(f"  用户:         {r.get('user', '-')}")
        print(f"  来源IP:       {r.get('host', '-')}")
        print(f"  set_name:     {r.get('set_name', '-')}")
        print(f"  set_ip:       {r.get('set_ip', '-')}")
        print(f"  时间戳:       {r.get('timestramp', '-')}")


def get_top_slow_sql(records, top_n=5, sort_by="query_time_avg"):
    """按指定字段排序，返回 TOP N 慢 SQL。"""
    if not records:
        return []

    def safe_float(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    sorted_records = sorted(records, key=lambda r: safe_float(r.get(sort_by, 0)), reverse=True)
    return sorted_records[:top_n]


def send_wechat_alert(slow_sql_records, top_n=5):
    """将 TOP N 慢 SQL 通过企业微信 markdown 格式发送告警。"""
    if not slow_sql_records:
        print(">>> 无慢SQL记录，跳过告警")
        return

    top_list = get_top_slow_sql(slow_sql_records, top_n=top_n, sort_by="query_time_avg")
    if not top_list:
        return

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(slow_sql_records)

    lines = [
        "## <font color=\"warning\">慢SQL告警</font>",
        f"> 集群: **{TARGET_CLUSTER_NAME}**",
        f"> 检测时间: {now_str}",
        f"> 近 {QUERY_WINDOW_MINUTES} 分钟共扫描到 **{total}** 条慢SQL",
        f"> 以下为平均耗时最高的 TOP {len(top_list)}：",
        "",
    ]

    for i, sql in enumerate(top_list, 1):
        sql_text = str(sql.get("example_sql", "-"))
        sql_compact = " ".join(sql_text.split())
        avg_time = sql.get("query_time_avg", "-")
        max_time = sql.get("query_time_max", "-")
        query_count = sql.get("query_count", "-")
        db_name = sql.get("db", "-")
        user_name = sql.get("user", "-")
        host_ip = sql.get("host", "-")
        rows_examined = sql.get("rows_examined_sum", "-")
        lock_avg = sql.get("lock_time_avg", "-")

        lines.append(f"**{i}. 平均耗时 {avg_time}s | 最大耗时 {max_time}s**")
        lines.append(f"> 数据库: {db_name} | 用户: {user_name} | 来源IP: {host_ip}")
        lines.append(f"> 执行次数: {query_count} | 扫描行数: {rows_examined} | 锁等待: {lock_avg}s")
        lines.append(f"> SQL:")
        lines.append(f"```sql")
        lines.append(f"{sql_compact}")
        lines.append(f"```")
        lines.append("")

    if total > top_n:
        lines.append(f"> 共 **{total}** 条慢SQL，此处仅展示 TOP {top_n}")

    content = "\n".join(lines)

    payload = {
        "msgtype": "markdown",
        "markdown": {"content": content},
    }

    try:
        resp = requests.post(WEBHOOK, json=payload, timeout=10)
        if resp.status_code == 200 and resp.json().get("errcode") == 0:
            print(f">>> 告警已发送: TOP {len(top_list)} 条慢SQL")
        else:
            print(f">>> 告警发送失败: {resp.text}")
    except requests.RequestException as e:
        print(f">>> 告警发送异常: {e}")


def main():
    token = getToken()
    if not token:
        print(">>> Token 获取失败，退出")
        exit(1)

    # ========== 第一步：从概览接口查找目标集群的 cmdbId ==========
    print(f"\n=== 查找目标集群「{TARGET_CLUSTER_NAME}」===")
    cmdb_id = getClusterCmdbId(token)

    if not cmdb_id:
        print(f">>> 未找到目标集群「{TARGET_CLUSTER_NAME}」，退出")
        exit(1)

    # ========== 第二步：获取慢 SQL 详情 ==========
    print(f"\n=== 获取集群「{TARGET_CLUSTER_NAME}」的慢SQL详情 ===")
    print(f"时间窗口: 最近 {QUERY_WINDOW_MINUTES} 分钟")
    slow_sql_records = getSlowSQLDetail(token, cmdb_id)

    # ========== 第三步：打印慢 SQL 列表 ==========
    print_slow_sql_list(slow_sql_records)

    # ========== 第四步：汇总统计 ==========
    print(f"\n=== 汇总统计 ===")
    print(f"慢SQL总数: {len(slow_sql_records)}")
    if slow_sql_records:
        # 平均耗时最高的 TOP 5
        top5 = get_top_slow_sql(slow_sql_records, top_n=5, sort_by="query_time_avg")
        print(f"\nTOP 5 平均耗时最高的慢SQL:")
        for i, s in enumerate(top5, 1):
            print(f"  {i}. [{s.get('query_time_avg', '-')}s]")
            print(f"     {s.get('example_sql', '-')}")

        # 执行次数最多的 TOP 5
        top5_count = sorted(slow_sql_records,
                            key=lambda r: float(r.get('query_count', 0)) if r.get('query_count') is not None else 0,
                            reverse=True)[:5]
        print(f"\nTOP 5 执行次数最多的慢SQL:")
        for i, s in enumerate(top5_count, 1):
            print(f"  {i}. [{s.get('query_count', '-')}次]")
            print(f"     {s.get('example_sql', '-')}")

    # ========== 第五步：发送告警 ==========
    send_wechat_alert(slow_sql_records)


if __name__ == "__main__":
    main()
