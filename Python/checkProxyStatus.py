# -*- coding: utf-8 -*-
"""
检查各 Proxy 集群中每个 proxy 的状态。
接口: /snc-ng-server/proxy/findByCluster
payload: {"params":{"realms":null,"runtimeOsEnv":"host"}}
status != 1 表示异常，需要通过企业微信机器人发送告警。
"""
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

# Proxy 状态映射（与平台定义一致: 1=在线/正常）
PROXY_STATUS_LABEL = {0: "离线", 1: "在线", 2: "异常"}


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


def getProxyStatusByCluster(token):
    """调用 findByCluster 接口，返回所有集群的 proxy 状态列表。"""
    api_url = url + "/snc-ng-server/proxy/findByCluster"

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Authorization": "admin",
        "Connection": "keep-alive",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": f"{url}",
        "Referer": f"{url}/snc-ng-server/proxy/findByCluster",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
        "accessToken": f"{token}",
        "snc-token": f"{token}",
    }

    request_data = {
        "params": {
            "realms": None,
            "runtimeOsEnv": "host"
        }
    }

    try:
        result = requests.post(
            url=api_url, json=request_data, headers=headers, verify=False
        )
        print(f"findByCluster 接口响应，状态码: {result.status_code}")

        if result.status_code == 200:
            response_data = json.loads(result.text)
            if response_data.get("msgCode") != 200:
                print(f"接口返回异常: {response_data.get('message', result.text)}")
                return []
            clusters = response_data.get("data", [])
            if not clusters:
                print("findByCluster 返回 data 为空")
                return []

            # 展开所有集群下的 proxy，附带集群名称
            all_proxies = []
            for cluster in clusters:
                cluster_name = cluster.get("clusterName", "未知集群")
                proxies = cluster.get("proxies")
                if not proxies:
                    continue
                for proxy in proxies:
                    proxy["_clusterName"] = cluster_name
                    all_proxies.append(proxy)

            print(f"共获取到 {len(clusters)} 个集群, {len(all_proxies)} 个 Proxy")
            return all_proxies
        else:
            print(f"findByCluster 请求失败，状态码: {result.status_code}")
            return []

    except Exception as e:
        print(f"获取 Proxy 状态异常: {e}")
        return []


def send_proxy_alert(abnormal_proxies):
    """
    将异常 proxy 列表组装为 markdown 内容，并发送到企业微信机器人。
    """
    if not abnormal_proxies:
        print(">>> 无异常 Proxy，跳过告警")
        return

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(abnormal_proxies)
    display_count = min(total, 10)

    lines = [
        "## <font color=\"warning\">Proxy 状态异常告警</font>",
        "> 检测时间: {}".format(now_str),
        "> 异常数量: **{}** 个".format(total),
        "",
    ]

    for i, proxy in enumerate(abnormal_proxies[:display_count], 1):
        proxy_name = proxy.get("proxyName", "-")
        cluster_name = proxy.get("_clusterName", proxy.get("clusterName", "-"))
        status = proxy.get("status")
        status_label = PROXY_STATUS_LABEL.get(status, f"未知({status})")
        proxy_ip = proxy.get("proxyIp", "-")
        heartbeat = proxy.get("latestHeartbeatTime")
        if heartbeat:
            try:
                heartbeat_str = datetime.datetime.fromtimestamp(heartbeat / 1000).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, OSError):
                heartbeat_str = str(heartbeat)
        else:
            heartbeat_str = "-"

        lines.append("**{}. {}**".format(i, proxy_name))
        lines.append("> 集群: {}".format(cluster_name))
        lines.append("> IP: {}".format(proxy_ip))
        lines.append("> 状态: <font color=\"warning\">{}</font>".format(status_label))
        lines.append("> 最后心跳: {}".format(heartbeat_str))
        lines.append("")

    if total > display_count:
        lines.append("> 共 **{}** 条异常，此处仅展示前 {} 条".format(total, display_count))

    content = "\n".join(lines)

    payload = {
        "msgtype": "markdown",
        "markdown": {"content": content},
    }

    try:
        resp = requests.post(WEBHOOK, json=payload, timeout=10)
        if resp.status_code == 200 and resp.json().get("errcode") == 0:
            print(f">>> 告警已发送: {total} 个异常 Proxy")
        else:
            print(f">>> 告警发送失败: {resp.text}")
    except requests.RequestException as e:
        print(f">>> 告警发送异常: {e}")



def main():
    token = getToken()
    if not token:
        print(">>> Token 获取失败，退出")
        exit(1)

    # ========== 获取所有 Proxy 状态 ==========
    print("\n=== Proxy 状态检查 ===")
    all_proxies = getProxyStatusByCluster(token)

    if not all_proxies:
        print(">>> 未获取到 Proxy 数据")
        return

    # ========== 按集群维度打印 ==========
    cluster_map = {}
    for proxy in all_proxies:
        cluster_name = proxy.get("_clusterName", proxy.get("clusterName", "未知集群"))
        cluster_map.setdefault(cluster_name, []).append(proxy)

    for cluster_name, proxies in cluster_map.items():
        print(f"\n--- {cluster_name} ({len(proxies)} 个 Proxy) ---")
        for p in proxies:
            status = p.get("status")
            status_label = PROXY_STATUS_LABEL.get(status, f"未知({status})")
            marker = " [异常]" if status != 1 else ""
            heartbeat = p.get("latestHeartbeatTime")
            if heartbeat:
                try:
                    hb_str = datetime.datetime.fromtimestamp(heartbeat / 1000).strftime("%Y-%m-%d %H:%M:%S")
                except (ValueError, OSError):
                    hb_str = str(heartbeat)
            else:
                hb_str = "-"
            print(f"  {p.get('proxyName', '-')} | IP: {p.get('proxyIp', '-')} | "
                  f"状态: {status_label} | 最后心跳: {hb_str}{marker}")

    # ========== 筛选异常 Proxy ==========
    abnormal_proxies = [p for p in all_proxies if p.get("status") != 1]
    print(f"\n=== 汇总 ===")
    print(f"Proxy 总数: {len(all_proxies)}, 异常: {len(abnormal_proxies)}")

    if abnormal_proxies:
        print("\n异常 Proxy 列表:")
        for p in abnormal_proxies:
            cluster_name = p.get("_clusterName", p.get("clusterName", "-"))
            status_label = PROXY_STATUS_LABEL.get(p.get("status"), f"未知({p.get('status')})")
            print(f"  [{status_label}] {p.get('proxyName', '-')} @ {cluster_name}")

    # ========== 发送告警（仅异常时发送） ==========
    if abnormal_proxies:
        send_proxy_alert(abnormal_proxies)
    else:
        print(">>> 所有 Proxy 状态正常，不发送通知")


if __name__ == "__main__":
    main()
