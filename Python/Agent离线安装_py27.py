#!/usr/local/easyops/python/bin/python
# encoding: utf-8
"""
Agent 离线安装脚本 (Python 2.7 版本)。
通过 CD 平台下发到目标主机执行，自动检测系统类型并安装 Agent。
流程：获取本机IP → 查询CMDB获取机房信息 → 选择对应Proxy → 下载并安装Agent
"""

import os
import sys
import json
import requests
import subprocess

# ========== 配置区 ==========
accessKey = "659a979b395a4ccb9dbfd8bbddc726dc"  # 接口凭证
proxy_url_gd = "http://10.129.134.27:10031"      # 观达机房代理
proxy_url_sx = "http://10.129.134.32:10031"      # 沙溪机房代理
domain = "https://ums-test.gf.com.cn"             # 域名

if sys.platform.startswith("linux"):
    import pwd      # 仅 Linux 需要 pwd 模块
    import getpass  # 获取当前用户名


def _run_service_cmd(script_path, action):
    """Linux 执行服务启停脚本：当前用户与 inputUser 一致则直接执行，否则 su 切换"""
    cmd = "bash {} {}".format(script_path, action)
    if getpass.getuser() == inputUser:
        return cmd
    else:
        return "su - {} -c '{}'".format(inputUser, cmd)


def _makedirs(path):
    """Python 2.7 兼容的 makedirs（模拟 exist_ok=True）"""
    try:
        os.makedirs(path)
    except OSError:
        if not os.path.isdir(path):
            raise


def check_and_create_user(user):
    """检查并创建 Agent 运行用户（仅 ums 用户支持自动创建）"""
    try:
        pwd.getpwnam(user)
        print("用户 {} 已存在".format(user))
        return True
    except KeyError:
        if user == "ums":
            print("用户 {} 不存在，正在自动创建...".format(user))
            # useradd -m: 创建家目录, -s: 指定默认 shell
            proc = subprocess.Popen(
                ['useradd', '-m', '-s', '/bin/bash', user],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            _, stderr = proc.communicate()
            if proc.returncode == 0:
                # passwd -l: 锁定密码禁止登录，仅允许服务使用
                subprocess.Popen(
                    ['passwd', '-l', user],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE
                ).communicate()
                print("用户 {} 创建成功".format(user))
                return True
            else:
                print("创建用户失败: {}".format(stderr))
                return False
        else:
            print("错误: 普通用户 {} 不存在，且不支持自动创建。".format(user))
            return False


def linux_agent_install(proxy_url, domain, agent_user, install_path, overwrite_enable=False):
    """Linux Agent 安装：停止旧服务 → mv 旧目录 → 下载并执行安装脚本 → 检查服务"""
    if os.path.isdir(install_path):
        if not overwrite_enable:
            print(">>> 安装目录 {} 已存在, overwrite_install=false, 跳过安装".format(install_path))
            return False
        print(">>> 安装目录 {} 已存在，正在清理旧 Agent...".format(install_path))
        import time
        # 先停止两个服务进程（必须以 inputUser 身份执行，jar 文件属主为 ums）
        for name in ("snc-ng-agent", "snc-ng-daemon"):
            stop_script = os.path.join(install_path, "snc-ng-agents", name, "snc_ng_server.sh")
            if os.path.isfile(stop_script):
                print("  >>> 执行停止脚本: {}".format(stop_script))
                subprocess.call(_run_service_cmd(stop_script, "stop"), shell=True)
        time.sleep(3)
        # mv 到 /tmp 带时间戳备份，避免旧文件残留影响新安装
        import datetime
        backup_path = "/tmp/{}_{}".format(
            os.path.basename(install_path),
            datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        )
        subprocess.call("mv {} {}".format(install_path, backup_path), shell=True)
        if os.path.isdir(install_path):
            print(">>> 清理目录失败，请手动删除: {}".format(install_path))
            return False

    _makedirs(install_path)

    # 通过 Proxy 转发到 UMS 下载安装脚本，管道传递给 bash 执行
    install_url = (
        "{proxy}/forward?targetUrl="
        "{domain}/snc-ng-server/agent/script/install_script.sh"
        "?installDaemon=true&preferIPv6=0&pskEnable=false"
    ).format(proxy=proxy_url, domain=domain)
    cmd = "set -o pipefail; curl '{}' | bash -s '{}' '{}'".format(
        install_url, agent_user, install_path
    )

    print(">>> 开始安装 Agent (用户: {}, 目录: {})...".format(agent_user, install_path))
    ret = subprocess.call(cmd, shell=True)
    if ret != 0:
        print(">>> Agent 安装失败")
        return False
    print(">>> Agent 安装完成")
    if check_services_running(install_path):
        print(">>> 所有服务检查通过")
        check_properties(install_path)
        return True
    else:
        print(">>> 服务检查未通过")
        return False


def windows_agent_install(proxy_url, domain, install_path, overwrite_enable=False):
    """Windows Agent 安装：停止旧服务 → 卸载旧服务 → 重命名旧目录 → 下载并安装 → 检查服务"""
    import time, glob, datetime

    script_name = "install_snc-ng-agent.bat"
    # 通过 Proxy 转发到 UMS 下载安装脚本
    target_url = (
        "{domain}/snc-ng-server/agent/script/install_script.bat"
        "?installDaemon=true&pskEnable=false"
    ).format(domain=domain)
    download_url = "{proxy}/forward?targetUrl={target}".format(
        proxy=proxy_url, target=target_url
    )
    services = ("snc-ng-daemon", "snc-ng-agent")

    # ========== 清理旧 Agent ==========
    # 流程: Stop脚本 → sc stop(轮询止) → Uninstall脚本 → move重命名 → rmdir
    if os.path.isdir(install_path):
        if not overwrite_enable:
            print(">>> 安装目录 {} 已存在, overwrite_install=false, 跳过安装".format(install_path))
            return False
        print(">>> 安装目录 {} 已存在，清理旧 Agent...".format(install_path))

        # sc query 检查哪些服务已注册在 SCM 中
        running_svcs = [
            svc for svc in services
            if subprocess.call("sc query {} >nul 2>&1".format(svc), shell=True) == 0
        ]
        if running_svcs:
            print("  >>> 运行中的服务: {}".format(running_svcs))
            # 第一步: Stop 脚本 — 通过应用自带的停止脚本停止服务
            for svc in running_svcs:
                pattern = os.path.join(install_path, "snc-ng-agents", "{}-*".format(svc), "bin")
                for agent_bin in sorted(glob.glob(pattern), reverse=True):
                    stop_bat = os.path.join(agent_bin, "Stop-{}.bat".format(svc))
                    if os.path.isfile(stop_bat):
                        print("  >>> Stop脚本: {}".format(stop_bat))
                        proc = subprocess.Popen(stop_bat, shell=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                        stdout, _ = proc.communicate()
                        if stdout:
                            print(stdout)
            time.sleep(3)
            # 第二步: sc stop — 通过 SCM 停止服务，轮询等待真正停止（必须在 Uninstall 之前）
            for svc in running_svcs:
                print("  >>> sc stop {}".format(svc))
                proc = subprocess.Popen(["sc", "stop", svc],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                stdout, _ = proc.communicate()
                if stdout:
                    print(stdout)
                # 轮询 sc query 直到状态变为 STOPPED，最多等 20 秒
                for attempt in range(10):
                    time.sleep(2)
                    check = subprocess.Popen(
                        ["sc", "query", svc],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    )
                    out, _ = check.communicate()
                    if "STOPPED" in out:
                        print("  >>> {} 已停止".format(svc))
                        break
                    if "RUNNING" not in out and "STOP_PENDING" not in out:
                        break  # 服务已被移除，无需继续等待
                else:
                    print("  >>> 警告: {} 未能在超时时间内停止".format(svc))
            # 第三步: Uninstall 脚本 — 从 SCM 中移除服务
            for svc in running_svcs:
                pattern = os.path.join(install_path, "snc-ng-agents", "{}-*".format(svc), "bin")
                for agent_bin in sorted(glob.glob(pattern), reverse=True):
                    uninstall_bat = os.path.join(agent_bin, "Uninstall-{}.bat".format(svc))
                    if os.path.isfile(uninstall_bat):
                        print("  >>> Uninstall脚本: {}".format(uninstall_bat))
                        proc = subprocess.Popen(uninstall_bat, shell=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                        stdout, _ = proc.communicate()
                        if stdout:
                            print(stdout)
            time.sleep(3)

        # 第四步: move 重命名旧目录到带时间戳的备份路径，绕过文件锁
        backup_path = "{}_{}".format(
            install_path.rstrip("\\"),
            datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        )
        print("  >>> 移除: {} -> {}".format(install_path, backup_path))
        subprocess.call(["cmd", "/c", "move", "/Y", install_path, backup_path], shell=True)

        if os.path.isdir(install_path):
            print(">>> 清理目录失败，请手动删除: {}".format(install_path))
            return False

        # 第五步: rmdir 删除备份目录，失败不阻塞安装流程
        subprocess.call(["cmd", "/c", "rmdir", "/s", "/q", backup_path], shell=True)
        if os.path.isdir(backup_path):
            print("  >>> 备份目录删除失败，请手动删除: {}".format(backup_path))

    # ========== 下载并安装 ==========
    _makedirs(install_path)
    script_path = os.path.join(install_path, script_name)

    # certutil 下载安装脚本（Windows 原生 HTTPS 下载，无需额外依赖）
    print(">>> 下载安装脚本: {}".format(download_url))
    proc = subprocess.Popen(
        ["certutil", "-urlcache", "-split", "-f", download_url, script_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    _, stderr = proc.communicate()
    if proc.returncode != 0:
        print(">>> 下载失败: {}".format(stderr))
        return False

    # 执行安装脚本，传入 install_path 参数
    print(">>> 执行安装脚本: {}".format(script_path))
    proc = subprocess.Popen(
        [script_path, install_path],
        cwd=install_path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=True,
    )
    # \n 自动确认脚本中的交互提示（如 pause）
    stdout, _ = proc.communicate(input="\n")
    if stdout:
        print(stdout)
    # batch 脚本的 pause 会掩盖真实返回码，需额外检测输出中的 "failed"
    if proc.returncode != 0 or "failed" in stdout.lower():
        print(">>> Agent 安装失败")
        return False
    print(">>> Agent 安装完成")

    # 安装后验证两个服务是否正常运行
    if check_services_running(install_path):
        print(">>> 所有服务检查通过")
        check_properties(install_path)
        return True
    else:
        print(">>> 服务检查未通过")
        return False


def check_services_running(install_path, max_retries=5, wait_seconds=5):
    """安装后验证 snc-ng-agent 和 snc-ng-daemon 是否在运行，未运行则尝试启动，最多重试 max_retries 次"""
    import time

    services = ("snc-ng-agent", "snc-ng-daemon")
    if sys.platform.startswith("win"):
        # Windows: sc query 检查服务状态，STOPPED 则 sc start 重试
        for svc in services:
            print(">>> 检查服务 {} 运行状态...".format(svc))
            for attempt in range(max_retries):
                proc = subprocess.Popen(
                    ["sc", "query", svc],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                stdout, _ = proc.communicate()
                if "RUNNING" in stdout:
                    print(">>> 服务 {} 正在运行".format(svc))
                    break
                elif "STOPPED" in stdout:
                    print(">>> 尝试启动服务 {} (第 {}/{})...".format(svc, attempt + 1, max_retries))
                    subprocess.call(["sc", "start", svc])
                    time.sleep(wait_seconds)
                else:
                    print(">>> 服务 {} 未找到，等待重试 (第 {}/{})...".format(svc, attempt + 1, max_retries))
                    time.sleep(wait_seconds)
            else:
                print(">>> 服务 {} 启动失败".format(svc))
                return False
    else:
        # Linux: ps -ef | grep 过滤进程，排除 grep 自身
        for svc in services:
            print(">>> 检查服务 {} 运行状态...".format(svc))
            for attempt in range(max_retries):
                p1 = subprocess.Popen(["ps", "-ef"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                p2 = subprocess.Popen(["grep", svc], stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                p1.stdout.close()
                stdout, _ = p2.communicate()
                # 过滤掉 grep 自身进程行，避免误判
                lines = [l for l in stdout.splitlines() if "grep" not in l]
                if lines:
                    print(">>> 服务 {} 正在运行".format(svc))
                    break
                else:
                    print(">>> 服务 {} 未运行，等待重试 (第 {}/{})...".format(svc, attempt + 1, max_retries))
                    time.sleep(wait_seconds)
            else:
                print(">>> 服务 {} 启动失败".format(svc))
                return False
    return True


def _cmdb_post(domain, token, api, data, error_msg="查询CMDB失败"):
    """CMDB POST 请求通用方法，返回 JSON 或 None"""
    url = "{}/{}".format(domain, api)
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "Accept": "*/*",
        "access-key": token,
        "snc-token": token,
    }
    try:
        response = requests.post(url=url, json=data, headers=headers)
        response.raise_for_status()
        return response.json()
    except (KeyError, IndexError):
        print(">>> {}: 数据不存在".format(error_msg))
        return None
    except requests.RequestException as e:
        print(">>> {}: {}".format(error_msg, e))
        return None


def _get_relation(domain, access_token, cmdbId, quote_ci_code, field, error_msg):
    """查询CMDB实例关系（机房 属于 数据中心 / 主机 属于 机房）"""
    result = _cmdb_post(domain, access_token,
        api="/snc-base-gateway/snc-cmdb-server/openapi/v1/instance/relation/getInstanceRelation",
        data={
            "params": {
                "cmdbId": cmdbId,
                "relationType": "属于",
                "quoteCiCode": quote_ci_code,
            }
        },
        error_msg=error_msg,
    )
    if result and result.get("data"):
        return result["data"][0][field]
    return None


def get_host_cmdbid(domain, access_token, host_ip):
    """根据主机 IP 查询 CMDB，返回 cmdbId"""
    result = _cmdb_post(domain, access_token,
        api="/snc-base-gateway/snc-cmdb-server/openapi/v1/instance/record/getInstances",
        data={
            "ciCode": "host",
            "status": [1],  # 仅查询在用状态的主机
            "attributeValues": [
                {"attributeCode": "host_ip", "logical": "eq", "attributeValue": host_ip}
            ],
        },
        error_msg="主机 {} 在CMDB中不存在".format(host_ip),
    )
    if result and result.get("data"):
        return result["data"][0]["cmdbId"]
    return None


def get_host_room(domain, access_token, cmdbId):
    """根据主机 cmdbId 查询所属机房的 cmdbId"""
    return _get_relation(domain, access_token, cmdbId,
        quote_ci_code="host_room", field="cmdb_id",
        error_msg="CMDB中未找到 cmdbId={} 的机房信息".format(cmdbId),
    )


def get_host_datacenter(domain, access_token, cmdbId):
    """根据机房 cmdbId 查询所属数据中心的名称"""
    return _get_relation(domain, access_token, cmdbId,
        quote_ci_code="host_datacenter", field="instance_name",
        error_msg="CMDB中未找到 cmdbId={} 的数据中心信息".format(cmdbId),
    )


def check_properties(install_path):
    """检查 agent.ip 配置是否与本机 IP 一致，不一致则停止服务 → 修改 → 重启"""
    import glob

    # Windows 路径带版本号: snc-ng-agent-1.0.3, Linux: snc-ng-agent
    pattern = os.path.join(install_path, "snc-ng-agents", "snc-ng-agent*", "config", "config.properties")
    matches = glob.glob(pattern)
    if not matches:
        print(">>> 配置文件未找到: {}".format(pattern))
        return False
    properties_path = matches[0]

    # 读取当前 agent.ip 值
    current_ip = None
    with open(properties_path, 'r') as f:
        for line in f:
            if line.strip().startswith("agent.ip="):
                current_ip = line.strip().split("=", 1)[1]
                break

    if current_ip is None:
        print(">>> 配置文件中未找到 agent.ip 配置项")
        return False

    target_ip = EASYOPS_LOCAL_IP
    if current_ip == target_ip:
        print(">>> agent.ip 配置正确: {}".format(current_ip))
        return True

    print(">>> agent.ip 配置不一致: 当前值={}, 应设为={}".format(current_ip, target_ip))
    return edit_properties(install_path, properties_path, current_ip, target_ip)


def edit_properties(install_path, properties_path, old_ip, new_ip):
    """停止 agent 和 daemon → 修改 agent.ip → 重启服务"""
    import time

    services = ("snc-ng-agent", "snc-ng-daemon")

    # ========== 停止服务 ==========
    print("  >>> 停止服务以修改配置...")
    if sys.platform.startswith("win"):
        for svc in services:
            subprocess.call(["sc", "stop", svc])
        # 轮询等待所有服务停止
        for svc in services:
            for attempt in range(10):
                time.sleep(2)
                proc = subprocess.Popen(
                    ["sc", "query", svc],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                out, _ = proc.communicate()
                if "STOPPED" in out:
                    print("  >>> {} 已停止".format(svc))
                    break
                if "RUNNING" not in out and "STOP_PENDING" not in out:
                    break
            else:
                print("  >>> 警告: {} 未能在超时时间内停止".format(svc))
    else:
        for svc in services:
            stop_script = os.path.join(install_path, "snc-ng-agents", svc, "snc_ng_server.sh")
            if os.path.isfile(stop_script):
                subprocess.call(_run_service_cmd(stop_script, "stop"), shell=True)
        time.sleep(3)

    # ========== 修改配置文件 ==========
    print("  >>> 修改 agent.ip: {} -> {}".format(old_ip, new_ip))
    with open(properties_path, 'r') as f:
        lines = f.readlines()
    with open(properties_path, 'w') as f:
        for line in lines:
            if line.strip().startswith("agent.ip="):
                f.write("agent.ip={}\n".format(new_ip))
            else:
                f.write(line)
    print("  >>> 配置文件已更新")

    # ========== 重启服务 ==========
    print("  >>> 重启服务...")
    if sys.platform.startswith("win"):
        for svc in services:
            subprocess.call(["sc", "start", svc])
        # 轮询等待所有服务启动
        for svc in services:
            for attempt in range(10):
                time.sleep(2)
                proc = subprocess.Popen(
                    ["sc", "query", svc],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                out, _ = proc.communicate()
                if "RUNNING" in out:
                    print("  >>> {} 已启动".format(svc))
                    break
            else:
                print("  >>> 警告: {} 启动失败".format(svc))
                return False
    else:
        for svc in services:
            start_script = os.path.join(install_path, "snc-ng-agents", svc, "snc_ng_server.sh")
            if os.path.isfile(start_script):
                subprocess.call(_run_service_cmd(start_script, "start"), shell=True)
        time.sleep(5)
        # 通过 ps -ef 验证进程已启动
        for svc in services:
            p1 = subprocess.Popen(["ps", "-ef"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            p2 = subprocess.Popen(["grep", svc], stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            p1.stdout.close()
            stdout, _ = p2.communicate()
            lines = [l for l in stdout.splitlines() if "grep" not in l]
            if lines:
                print("  >>> {} 已启动".format(svc))
            else:
                print("  >>> 警告: {} 启动失败".format(svc))
                return False

    print(">>> agent.ip 修复完成")
    return True


def getToken():
    # 登录接口
    loginUrl = domain + "/user/passport/loginCode"
    username = "agent"
    password = "BA19bBEN5a+ym7MJxWsndnzpDVRYSuGW7Rjf+7xvrjnVNlBMMYToZhnu0pBzM+4e38Vgw0AzWFd2AEGiprYGEaM5WRLhSbNWNS1kxN+9ef9LpahSRO2+emJGvZe/Nnu8gRRNPchYWhUSPPzBTrfpzH+QJ1Lt2PxCDnGp+PsQJpU="

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


def host_access_management(host_ip, template_ids, cmdb_id="", cluster_id=3, target_id=200):
    """主机接入管理：获取 instanceId → 关联资源 → 绑定模板 → 保存"""
    token = getToken()
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "snc-token": token,
    }

    # 1. 查询主机 instanceId
    result = requests.post(
        url=domain + "/snc-platform-mapping/joinInfo/resourceInstance/list",
        json={
            "params": {
                "condition": {
                    "resourceId": 24,
                    "resourceCode": "host",
                    "resourceName": "主机",
                    "parentCode": "logical_host",
                    "instanceName": host_ip,
                },
                "pagination": {"pagenum": 1, "pagesize": 50},
            }
        },
        headers=headers, verify=False,
    )
    instance_id = result.json()["data"]["records"][0]["instanceId"]
    print(">>> 主机接入 instanceId: {}".format(instance_id))

    # 2. 关联资源
    requests.post(
        url=domain + "/snc-ng-server/resource/join",
        json={"params": {"ids": [instance_id]}},
        headers=headers, verify=False,
    )
    print(">>> 关联资源完成")

    # 3. 绑定监控模板
    if template_ids:
        requests.post(
            url=domain + "/snc-platform-mapping/monitor/template/hostRelTemplateBatch",
            json={"params": [{"cmdbId": cmdb_id, "templateIds": template_ids}]},
            headers=headers, verify=False,
        )
        print(">>> 绑定模板完成: {}".format(template_ids))

    # 4. 保存接入配置
    requests.post(
        url=domain + "/snc-ng-server/resource/saveOrUpdateJoin",
        json={
            "params": [{
                "clusterId": cluster_id,
                "instanceId": instance_id,
                "instanceName": host_ip,
                "joinMode": 3,
                "targetId": target_id,
            }]
        },
        headers=headers, verify=False,
    )
    print(">>> 主机接入保存完成")


def main():
    """入口：获取本机IP → 查询CMDB获取机房/数据中心 → 选择对应Proxy → 安装Agent"""

    # ========== 参数区 ==========
    # 由 CD 平台注入: EASYOPS_LOCAL_IP (本机IP), inputUser (执行用户), overwrite_install (覆盖安装)
    agent_host = EASYOPS_LOCAL_IP
    agent_user = inputUser
    overwrite_installation = str(overwrite_install).lower() in ("true", "1")

    # 安装路径: Linux /opt/gf-ums, Windows C:\gf-ums
    if sys.platform.startswith("win"):
        install_path = r"C:\gf-ums"
    else:
        install_path = "/opt/gf-ums"

    # ========== 查询CMDB并选择代理 ==========
    # 默认使用观达代理，查询到沙溪数据中心时切换
    proxy_url = proxy_url_gd
    host_cmdbId = get_host_cmdbid(domain, accessKey, agent_host)
    if host_cmdbId:
        host_room_cmdbId = get_host_room(domain, accessKey, host_cmdbId)
        host_datacenter_name = get_host_datacenter(domain, accessKey, host_room_cmdbId)

        if host_datacenter_name and "gzsx" in host_datacenter_name.lower():
            proxy_url = proxy_url_sx
        print(">>> 数据中心: {}, 使用代理: {}".format(host_datacenter_name, proxy_url))
    else:
        print(">>> CMDB未查到主机信息，默认使用代理: {}".format(proxy_url))

    # ========== 安装 Agent ==========
    install_ok = False
    template_ids = []
    if sys.platform.startswith("win"):
        print(">>> 检测到 Windows 系统，开始安装 Agent...")
        install_ok = windows_agent_install(proxy_url, domain, install_path, overwrite_installation)
        template_ids = [178]  # Windows 模板
    elif sys.platform.startswith("linux"):
        print(">>> 检测到 Linux 系统，开始安装 Agent...")
        if agent_user and not check_and_create_user(agent_user):
            print(">>> 用户检查失败，安装终止")
            return
        install_ok = linux_agent_install(proxy_url, domain, agent_user, install_path, overwrite_installation)
        template_ids = [210]  # Linux 模板
    else:
        print(">>> 不支持的系统类型: {}，跳过 Agent 安装".format(sys.platform))

    # ========== 关联监控模板 ==========
    if install_ok and host_cmdbId:
        host_access_management(agent_host, template_ids, cmdb_id=host_cmdbId)
    elif not install_ok:
        print(">>> Agent 安装失败，跳过模板关联")


if __name__ == '__main__':
    main()
