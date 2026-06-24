#!/usr/local/easyops/python/bin/python
# encoding: utf-8
"""
Agent 离线安装脚本 (Python 3 版本)。
通过 CD 平台下发到目标主机执行，自动检测系统类型并安装 Agent。
流程：获取本机IP → 查询CMDB获取机房信息 → 选择对应Proxy → 下载并安装Agent
"""

import os
import sys
import requests
import subprocess

if sys.platform.startswith("linux"):
    import pwd      # 仅 Linux 需要 pwd 模块
    import getpass  # 获取当前用户名

# ========== 配置区 ==========
accessKey = "659a979b395a4ccb9dbfd8bbddc726dc"  # 接口凭证
proxy_url_gd = "http://10.129.134.27:10031"      # 观达机房代理
proxy_url_sx = "http://10.129.134.32:10031"      # 沙溪机房代理
domain = "https://ums-test.gf.com.cn"             # 域名


def _run_service_cmd(script_path, action):
    """Linux 执行服务启停脚本：当前用户与 inputUser 一致则直接执行，否则 su 切换"""
    cmd = f"bash {script_path} {action}"
    if getpass.getuser() == inputUser:
        return cmd
    else:
        return f"su - {inputUser} -c '{cmd}'"


def check_and_create_user(user):
    """检查并创建 Agent 运行用户（仅 ums 用户支持自动创建）"""
    try:
        pwd.getpwnam(user)
        print(f"用户 {user} 已存在")
        return True
    except KeyError:
        if user == "ums":
            print(f"用户 {user} 不存在，正在自动创建...")
            # useradd -m: 创建家目录, -s: 指定默认 shell
            result = subprocess.run(
                ['useradd', '-m', '-s', '/bin/bash', user],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                # passwd -l: 锁定密码禁止登录，仅允许服务使用
                subprocess.run(['passwd', '-l', user], capture_output=True)
                print(f"用户 {user} 创建成功")
                return True
            else:
                print(f"创建用户失败: {result.stderr}")
                return False
        else:
            print(f"错误: 普通用户 {user} 不存在，且不支持自动创建。")
            return False


def linux_agent_install(proxy_url, domain, agent_user, install_path, overwrite_enable=False):
    """Linux Agent 安装：停止旧服务 → mv 旧目录 → 下载并执行安装脚本 → 检查服务"""
    if os.path.isdir(install_path):
        if not overwrite_enable:
            print(f">>> 安装目录 {install_path} 已存在, overwrite_install=false, 跳过安装")
            return False
        print(f">>> 安装目录 {install_path} 已存在，正在清理旧 Agent...")
        import time
        # 先停止两个服务进程（必须以 inputUser 身份执行，jar 文件属主为 ums）
        for name in ("snc-ng-agent", "snc-ng-daemon"):
            stop_script = os.path.join(install_path, "snc-ng-agents", name, "snc_ng_server.sh")
            if os.path.isfile(stop_script):
                print(f"  >>> 执行停止脚本: {stop_script}")
                subprocess.run(_run_service_cmd(stop_script, "stop"), shell=True)
        time.sleep(3)
        # mv 到 /tmp 带时间戳备份，避免旧文件残留影响新安装
        import datetime
        backup_path = "/tmp/{}_{}".format(
            os.path.basename(install_path),
            datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        )
        subprocess.run(f"mv {install_path} {backup_path}", shell=True)
        if os.path.isdir(install_path):
            print(f">>> 清理目录失败，请手动删除: {install_path}")
            return False
    os.makedirs(install_path, exist_ok=True)

    # 通过 Proxy 转发到 UMS 下载安装脚本，管道传递给 bash 执行
    install_url = (
        f"{proxy_url}/forward?targetUrl="
        f"{domain}/snc-ng-server/agent/script/install_script.sh"
        f"?installDaemon=true&preferIPv6=0&pskEnable=false"
    )
    cmd = f"set -o pipefail; curl '{install_url}' | bash -s '{agent_user}' '{install_path}'"

    print(f">>> 开始安装 Agent (用户: {agent_user}, 目录: {install_path})...")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
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
        f"{domain}/snc-ng-server/agent/script/install_script.bat"
        f"?installDaemon=true&pskEnable=false"
    )
    download_url = f"{proxy_url}/forward?targetUrl={target_url}"
    services = ("snc-ng-daemon", "snc-ng-agent")

    # ========== 清理旧 Agent ==========
    # 流程: Stop脚本 → sc stop(轮询等待停止) → Uninstall脚本 → move重命名 → rmdir
    if os.path.isdir(install_path):
        if not overwrite_enable:
            print(f">>> 安装目录 {install_path} 已存在, overwrite_install=false, 跳过安装")
            return False
        print(f">>> 安装目录 {install_path} 已存在，清理旧 Agent...")

        # sc query 检查哪些服务已注册在 SCM 中
        running_svcs = [
            svc for svc in services
            if subprocess.call(f"sc query {svc} >nul 2>&1.py", shell=True) == 0
        ]
        if running_svcs:
            print(f"  >>> 运行中的服务: {running_svcs}")
            # 第一步: Stop 脚本 — 通过应用自带的停止脚本停止服务
            for svc in running_svcs:
                pattern = os.path.join(install_path, "snc-ng-agents", f"{svc}-*", "bin")
                for agent_bin in sorted(glob.glob(pattern), reverse=True):
                    stop_bat = os.path.join(agent_bin, f"Stop-{svc}.bat")
                    if os.path.isfile(stop_bat):
                        print(f"  >>> Stop脚本: {stop_bat}")
                        result = subprocess.run(stop_bat, shell=True,
                            capture_output=True, text=True)
                        if result.stdout:
                            print(result.stdout)
            time.sleep(3)
            # 第二步: sc stop — 通过 SCM 停止服务，轮询等待真正停止（必须在 Uninstall 之前）
            for svc in running_svcs:
                print(f"  >>> sc stop {svc}")
                result = subprocess.run(["sc", "stop", svc],
                    capture_output=True, text=True)
                if result.stdout:
                    print(result.stdout)
                # 轮询 sc query 直到状态变为 STOPPED，最多等 20 秒
                for attempt in range(10):
                    time.sleep(2)
                    check = subprocess.run(
                        ["sc", "query", svc],
                        capture_output=True, text=True,
                    )
                    if "STOPPED" in check.stdout:
                        print(f"  >>> {svc} 已停止")
                        break
                    if "RUNNING" not in check.stdout and "STOP_PENDING" not in check.stdout:
                        break  # 服务已被移除，无需继续等待
                else:
                    print(f"  >>> 警告: {svc} 未能在超时时间内停止")
            # 第三步: Uninstall 脚本 — 从 SCM 中移除服务
            for svc in running_svcs:
                pattern = os.path.join(install_path, "snc-ng-agents", f"{svc}-*", "bin")
                for agent_bin in sorted(glob.glob(pattern), reverse=True):
                    uninstall_bat = os.path.join(agent_bin, f"Uninstall-{svc}.bat")
                    if os.path.isfile(uninstall_bat):
                        print(f"  >>> Uninstall脚本: {uninstall_bat}")
                        result = subprocess.run(uninstall_bat, shell=True,
                            capture_output=True, text=True)
                        if result.stdout:
                            print(result.stdout)
            time.sleep(3)

        # 第四步: move 重命名旧目录到带时间戳的备份路径，绕过文件锁
        backup_path = "{}_{}".format(
            install_path.rstrip("\\"),
            datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        )
        print(f"  >>> 移除: {install_path} -> {backup_path}")
        subprocess.run(["cmd", "/c", "move", "/Y", install_path, backup_path], shell=True)

        if os.path.isdir(install_path):
            print(f">>> 清理目录失败，请手动删除: {install_path}")
            return False

        # 第五步: rmdir 删除备份目录，失败不阻塞安装流程
        subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", backup_path], shell=True)
        if os.path.isdir(backup_path):
            print(f"  >>> 备份目录删除失败，请手动删除: {backup_path}")

    # ========== 下载并安装 ==========
    os.makedirs(install_path, exist_ok=True)
    script_path = os.path.join(install_path, script_name)

    # certutil 下载安装脚本（Windows 原生 HTTPS 下载，无需额外依赖）
    print(f">>> 下载安装脚本: {download_url}")
    result = subprocess.run(
        ["certutil", "-urlcache", "-split", "-f", download_url, script_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f">>> 下载失败: {result.stderr}")
        return False

    # 执行安装脚本，传入 install_path 参数
    print(f">>> 执行安装脚本: {script_path}")
    result = subprocess.run(
        [script_path, install_path],
        cwd=install_path,
        input="\n",  # \n 自动确认脚本中的交互提示（如 pause）
        capture_output=True, text=True, shell=True,
    )
    if result.stdout:
        print(result.stdout)
    # batch 脚本的 pause 会掩盖真实返回码，需额外检测输出中的 "failed"
    if result.returncode != 0 or "failed" in result.stdout.lower():
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
            print(f">>> 检查服务 {svc} 运行状态...")
            for attempt in range(max_retries):
                result = subprocess.run(
                    ["sc", "query", svc],
                    capture_output=True, text=True,
                )
                if "RUNNING" in result.stdout:
                    print(f">>> 服务 {svc} 正在运行")
                    break
                elif "STOPPED" in result.stdout:
                    print(f">>> 尝试启动服务 {svc} (第 {attempt + 1}/{max_retries})...")
                    subprocess.run(["sc", "start", svc])
                    time.sleep(wait_seconds)
                else:
                    print(f">>> 服务 {svc} 未找到，等待重试 (第 {attempt + 1}/{max_retries})...")
                    time.sleep(wait_seconds)
            else:
                print(f">>> 服务 {svc} 启动失败")
                return False
    else:
        # Linux: ps -ef | grep 过滤进程，排除 grep 自身
        for svc in services:
            print(f">>> 检查服务 {svc} 运行状态...")
            for attempt in range(max_retries):
                result = subprocess.run(
                    f"ps -ef | grep {svc} | grep -v grep",
                    shell=True, capture_output=True, text=True,
                )
                if result.stdout.strip():
                    print(f">>> 服务 {svc} 正在运行")
                    break
                else:
                    print(f">>> 服务 {svc} 未运行，等待重试 (第 {attempt + 1}/{max_retries})...")
                    time.sleep(wait_seconds)
            else:
                print(f">>> 服务 {svc} 启动失败")
                return False
    return True


def check_properties(install_path):
    """检查 agent.ip 配置是否与本机 IP 一致，不一致则停止服务 → 修改 → 重启"""
    import glob

    # Windows 路径带版本号: snc-ng-agent-1.py.0.3, Linux: snc-ng-agent
    pattern = os.path.join(install_path, "snc-ng-agents", "snc-ng-agent*", "config", "config.properties")
    matches = glob.glob(pattern)
    if not matches:
        print(f">>> 配置文件未找到: {pattern}")
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
        print(f">>> agent.ip 配置正确: {current_ip}")
        return True

    print(f">>> agent.ip 配置不一致: 当前值={current_ip}, 应设为={target_ip}")
    return edit_properties(install_path, properties_path, current_ip, target_ip)


def edit_properties(install_path, properties_path, old_ip, new_ip):
    """停止 agent 和 daemon → 修改 agent.ip → 重启服务"""
    import time

    services = ("snc-ng-agent", "snc-ng-daemon")

    # ========== 停止服务 ==========
    print("  >>> 停止服务以修改配置...")
    if sys.platform.startswith("win"):
        for svc in services:
            subprocess.run(["sc", "stop", svc])
        # 轮询等待所有服务停止
        for svc in services:
            for attempt in range(10):
                time.sleep(2)
                result = subprocess.run(
                    ["sc", "query", svc],
                    capture_output=True, text=True,
                )
                if "STOPPED" in result.stdout:
                    print(f"  >>> {svc} 已停止")
                    break
                if "RUNNING" not in result.stdout and "STOP_PENDING" not in result.stdout:
                    break
            else:
                print(f"  >>> 警告: {svc} 未能在超时时间内停止")
    else:
        for svc in services:
            stop_script = os.path.join(install_path, "snc-ng-agents", svc, "snc_ng_server.sh")
            if os.path.isfile(stop_script):
                subprocess.run(_run_service_cmd(stop_script, "stop"), shell=True)
        time.sleep(3)

    # ========== 修改配置文件 ==========
    print(f"  >>> 修改 agent.ip: {old_ip} -> {new_ip}")
    with open(properties_path, 'r') as f:
        lines = f.readlines()
    with open(properties_path, 'w') as f:
        for line in lines:
            if line.strip().startswith("agent.ip="):
                f.write(f"agent.ip={new_ip}\n")
            else:
                f.write(line)
    print("  >>> 配置文件已更新")

    # ========== 重启服务 ==========
    print("  >>> 重启服务...")
    if sys.platform.startswith("win"):
        for svc in services:
            subprocess.run(["sc", "start", svc])
        # 轮询等待所有服务启动
        for svc in services:
            for attempt in range(10):
                time.sleep(2)
                result = subprocess.run(
                    ["sc", "query", svc],
                    capture_output=True, text=True,
                )
                if "RUNNING" in result.stdout:
                    print(f"  >>> {svc} 已启动")
                    break
            else:
                print(f"  >>> 警告: {svc} 启动失败")
                return False
    else:
        for svc in services:
            start_script = os.path.join(install_path, "snc-ng-agents", svc, "snc_ng_server.sh")
            if os.path.isfile(start_script):
                subprocess.run(_run_service_cmd(start_script, "start"), shell=True)
        time.sleep(5)
        # 通过 ps -ef 验证进程已启动
        for svc in services:
            result = subprocess.run(
                f"ps -ef | grep {svc} | grep -v grep",
                shell=True, capture_output=True, text=True,
            )
            if result.stdout.strip():
                print(f"  >>> {svc} 已启动")
            else:
                print(f"  >>> 警告: {svc} 启动失败")
                return False

    print(">>> agent.ip 修复完成")
    return True


def _cmdb_post(domain, access_token, api, data, error_msg="查询CMDB失败"):
    """CMDB POST 请求通用方法，返回 JSON 或 None"""
    url = f"{domain}/{api}"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "Accept": "*/*",
        "access-key": access_token,
    }
    try:
        response = requests.post(url=url, json=data, headers=headers)
        response.raise_for_status()
        return response.json()
    except (KeyError, IndexError):
        print(f">>> {error_msg}: 数据不存在")
        return None
    except requests.RequestException as e:
        print(f">>> {error_msg}: {e}")
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
        error_msg=f"主机 {host_ip} 在CMDB中不存在",
    )
    if result and result.get("data"):
        return result["data"][0]["cmdbId"]
    return None


def get_host_room(domain, access_token, cmdbId):
    """根据主机 cmdbId 查询所属机房的 cmdbId"""
    return _get_relation(domain, access_token, cmdbId,
        quote_ci_code="host_room", field="cmdb_id",
        error_msg=f"CMDB中未找到 cmdbId={cmdbId} 的机房信息",
    )


def get_host_datacenter(domain, access_token, cmdbId):
    """根据机房 cmdbId 查询所属数据中心的名称"""
    return _get_relation(domain, access_token, cmdbId,
        quote_ci_code="host_datacenter", field="instance_name",
        error_msg=f"CMDB中未找到 cmdbId={cmdbId} 的数据中心信息",
    )


def main():
    """入口：获取本机IP → 查询CMDB获取机房/数据中心 → 选择对应Proxy → 安装Agent"""

    # ========== 参数区 ==========
    # 由 CD 平台注入: EASYOPS_LOCAL_IP (本机IP), inputUser (执行用户), overwrite_install (覆盖安装)
    # agent_host = EASYOPS_LOCAL_IP
    agent_host = "10.129.134.24"
    # agent_user = inputUser
    agent_user = "ums"
    # overwrite_installation = str(overwrite_install).lower() in ("true", "1.py")
    overwrite_installation = "false"
    # 安装路径: Linux /opt/gf-ums, Windows C:\gf-ums
    if sys.platform.startswith("win"):
        install_path = r"C:\gf-ums"
    else:
        install_path = "/opt/gf-ums"

    # ========== 查询CMDB并选择代理 ==========
    # 默认使用广东代理，查询到汕尾数据中心时切换
    proxy_url = proxy_url_gd
    host_cmdbId = get_host_cmdbid(domain, accessKey, agent_host)
    if host_cmdbId:
        host_room_cmdbId = get_host_room(domain, accessKey, host_cmdbId)
        host_datacenter_name = get_host_datacenter(domain, accessKey, host_room_cmdbId)

        if host_datacenter_name and "gzsx" in host_datacenter_name.lower():
            proxy_url = proxy_url_sx
        print(f">>> 数据中心: {host_datacenter_name}, 使用代理: {proxy_url}")
    else:
        print(f">>> CMDB未查到主机信息，默认使用代理: {proxy_url}")

    # ========== 安装 Agent ==========
    # if sys.platform.startswith("win"):
    #     print(">>> 检测到 Windows 系统，开始安装 Agent...")
    #     windows_agent_install(proxy_url, domain, install_path, overwrite_installation)
    # elif sys.platform.startswith("linux"):
    #     print(">>> 检测到 Linux 系统，开始安装 Agent...")
    #     if agent_user and not check_and_create_user(agent_user):
    #         print(">>> 用户检查失败，安装终止")
    #         return
    #     linux_agent_install(proxy_url, domain, agent_user, install_path, overwrite_installation)
    # else:
    #     print(f">>> 不支持的系统类型: {sys.platform}，跳过 Agent 安装")
    #

if __name__ == '__main__':
    main()
