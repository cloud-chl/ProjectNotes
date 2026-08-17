# -*- coding:utf-8 -*-

import argparse
import json
import os
import sys
import time
from datetime import datetime, date, timedelta

import requests
import urllib3

from clickhouse_driver import Client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def log(msg: str):
    """运行日志输出到 stderr，保持 stdout 只输出最终 JSON（平台解析用）"""
    print(msg, file=sys.stderr)


def fail(msg: str):
    """致命配置错误：stderr 打详细日志，stdout 输出错误 JSON（避免"无输出"难排查），非 0 退出"""
    print(">>> " + msg, file=sys.stderr)
    try:
        print(json.dumps({"error": msg}, ensure_ascii=False), end="", flush=True)
    except Exception:
        pass
    sys.exit(1)


def _resolve_timeout(env_var: str, default):
    """读取环境变量中的超时时间（秒）；空值或未设置时返回默认值，None 表示不限制。"""
    if env_var in os.environ and os.environ[env_var] != "":
        return float(os.environ[env_var])
    return default


def _env_str(name: str, default: str = "") -> str:
    """读取环境变量字符串；未设置或为空时返回默认值"""
    v = os.environ.get(name, "")
    return v if v != "" else default


# ==================== 配置区 ====================

# ---- CMDB 接口（PYSCRIPT_SECRETS.cmdb 未提供时，用环境变量或默认值兜底）----
CMDB_DOMAIN = _env_str("PYSCRIPT_CMDB_DOMAIN", "https://ums-test.gf.com.cn")
CMDB_ACCESS_KEY = _env_str("PYSCRIPT_CMDB_ACCESS_KEY", "3550c2efecfc45fca81b76115f620f7f")

# ---- 告警消息字段（webhook 告警接入字段，见 getTaskStateToKafka.py）----
ALARM_APP_NAME = "本平台"   # appName，按平台约定调整
ALARM_PRIORITY = 2                    # priority: 1=紧急 2=严重 3=一般（参考脚本默认3）
TRIGGER_ID = "mem_p95_alarm"          # triggerId，平台按此关联规则，可自定义字符串

# ---- 指标名（metric_dbl.mappingMetricName，精确匹配，大小写不敏感）----
MEMORY_METRIC_NAMES = ["物理内存使用率", "内存使用率_zabbix"]
SWAP_METRIC_NAMES = ["可用交换空间百分比"]
EXACT_METRIC_NAMES = MEMORY_METRIC_NAMES + SWAP_METRIC_NAMES

# 指标名称归一化：变体 + 大小写 → 规范名（参照 host_p95_metric.py 的 METRIC_CANONICAL_MAP）
METRIC_CANONICAL_MAP = {
    "物理内存使用率": "物理内存使用率",
    "内存使用率_zabbix": "物理内存使用率",
    "可用交换空间百分比": "可用交换空间百分比",
}
MEMORY_CANONICAL = "物理内存使用率"
SWAP_CANONICAL = "可用交换空间百分比"

# ---- 判断基线日：Windows 110% / Linux 换页 110% 对比所用基准 ----
#   prev_workday = 前一天（若前一天是周末则直接取上工作日，周一取上周五）
BASELINE_DAY = "prev_workday"

# ---- 告警阈值 ----
WINDOWS_MEM_P95_THRESHOLD = 80.0    # Windows: 内存使用率P95 >= 80%
WINDOWS_GROWTH_RATIO = 1.1          # Windows: 当天P95 >= 前一天P95 * 1.1

LINUX_MEM_P95_THRESHOLD = 80.0      # Linux(换页关闭): 内存使用率P95 >= 80%
LINUX_SWAP_GROWTH_RATIO = 1.1        # Linux(换页开启): 当天换页 >= 前一天换页 * 110%

# Linux 换页开关判定：enabled=恒开 / disabled=恒关 / auto=有换页数据即视为开启
SWAP_CHECK_MODE = "auto"


# ==================== ClickHouse（参照 host_p95_metric.py） ====================

SQL_P95 = """
SELECT
    cmdbId,
    resourceName,
    metricCode,
    metricName,
    mappingMetricName,
    quantile(0.95)(value) AS p95,
    max(clock) AS max_clock
FROM default.metric_dbl
PREWHERE startsWith(cmdbId, 'host_')
WHERE _partition_id IN ({partitions})
  AND clock >= {start_ms}
  AND clock < {end_ms}
  AND startsWith(cmdbId, 'host_')
  AND ({metric_cond})
GROUP BY cmdbId, resourceName, metricCode, metricName, mappingMetricName
"""

ALL_METRIC_NAMES = EXACT_METRIC_NAMES


class ClickHouseHelper:
    def __init__(self, cfg: dict):
        connect_timeout = _resolve_timeout("PYSCRIPT_CH_CONNECT_TIMEOUT", 10)
        send_receive_timeout = _resolve_timeout("PYSCRIPT_CH_SEND_RECEIVE_TIMEOUT", 1010)
        max_execution_time = _resolve_timeout("PYSCRIPT_CH_MAX_EXECUTION_TIME", 1000)
        self.client = Client(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["username"],
            password=cfg["password"],
            database=cfg["database"],
            connect_timeout=connect_timeout,
            send_receive_timeout=send_receive_timeout,
            settings={"max_execution_time": max_execution_time},
        )

    def query(self, sql: str) -> list:
        data, col_types = self.client.execute(sql, with_column_types=True)
        columns = [c[0] for c in col_types]
        return [dict(zip(columns, row)) for row in data]


# ==================== 时间窗口 ====================

def prev_workday(d: date) -> date:
    """d 之前最近的一个工作日（周一~周五，周一取上周五）"""
    cur = d - timedelta(days=1)
    while cur.weekday() >= 5:  # 5=周六 6=周日
        cur -= timedelta(days=1)
    return cur


def build_windows(alarm_date: date) -> dict:
    """返回 {key: {"date": date, "start_ms": int, "end_ms": int}}，均为 08:00-16:00

    prev_workday = 前一天（若前一天是周末则直接取上工作日，周一取上周五）
    """
    windows = {}
    for key, d in (
        ("today", alarm_date),
        ("prev_workday", prev_workday(alarm_date)),
    ):
        start = datetime(d.year, d.month, d.day, 8, 0, 0)
        end = datetime(d.year, d.month, d.day, 16, 0, 0)
        windows[key] = {
            "date": d,
            "start_ms": int(start.timestamp() * 1000),
            "end_ms": int(end.timestamp() * 1000),
        }
    return windows


# ==================== 指标分类与采集（参照 host_p95_metric.py 的归一化/去重写法） ====================

def build_metric_cond(names: list) -> str:
    """指标名大小写不敏感精确匹配（参照 host_p95_metric.py 的 EXACT_METRIC_NAMES 写法）"""
    conds = ["lower(mappingMetricName) = '%s'" % n.lower() for n in names]
    return " OR ".join(conds)


def _normalize_metric_name(name: str) -> str:
    """大小写不敏感匹配规范名（如 内存使用率_zabbix → 物理内存使用率）；未映射的名称原样返回"""
    lower_name = name.lower()
    for variant, canonical in METRIC_CANONICAL_MAP.items():
        if variant.lower() == lower_name:
            return canonical
    return name


def classify_metric(mapping_name: str):
    """mappingMetricName → 指标组：memory / swap / None（先按规范名归一化再分组）"""
    canonical = _normalize_metric_name(mapping_name)
    if canonical == MEMORY_CANONICAL:
        return "memory"
    if canonical == SWAP_CANONICAL:
        return "swap"
    return None


def query_window_p95(ch: ClickHouseHelper, start_ms: int, end_ms: int, partitions_sql: str) -> list:
    sql = SQL_P95.format(
        partitions=partitions_sql,
        start_ms=start_ms,
        end_ms=end_ms,
        metric_cond=build_metric_cond(ALL_METRIC_NAMES),
    )
    return ch.query(sql)


def collect_p95(ch: ClickHouseHelper, windows: dict) -> dict:
    """返回 result[group][window_key][host_ip] = {"p95","metricCode","metricName","clock"}

    host_ip 直接取 ClickHouse 的 resourceName 字段（即主机 IP），不依赖 MySQL/CMDB 映射
    优化：每个窗口只查自己日期的分区（避免跨分区冗余扫描）
    """
    result = {}
    no_ip = 0
    for wk, w in windows.items():
        partition = "'%s'" % w["date"].strftime("%Y%m%d")
        rows = query_window_p95(ch, w["start_ms"], w["end_ms"], partition)

        for r in rows:
            if r["p95"] is None:
                continue
            host_ip = r.get("resourceName") or ""
            if not host_ip:
                no_ip += 1
                continue
            grp = classify_metric(r["mappingMetricName"])
            if grp is None:
                continue

            rec = {
                "p95": round(float(r["p95"]), 2),
                "metricCode": r["metricCode"],
                "metricName": _normalize_metric_name(r["mappingMetricName"]),
                "clock": r["max_clock"],
            }
            bucket = result.setdefault(grp, {}).setdefault(wk, {})
            if host_ip not in bucket:
                bucket[host_ip] = rec
    if no_ip:
        log(">>> 警告: {} 条指标缺少 resourceName（无法识别主机IP，已跳过）".format(no_ip))
    return result


# ==================== CMDB（参照 Agent离线安装脚本 get_host_cmdbid） ====================

class CmdbClient:
    """CMDB 主机属性查询：按 host_ip 查 os_type / host_type / host_name 等，带缓存

    host_ip 直接来自 ClickHouse 的 resourceName 字段，无需 cmdbId→host_ip 映射
    """

    GET_INSTANCES_API = "/snc-base-gateway/snc-cmdb-server/openapi/v1/instance/record/getInstances"

    def __init__(self, domain: str, access_key: str, timeout: int = 30):
        self.domain = domain.rstrip("/")
        self.access_key = access_key
        self.timeout = timeout
        self._cache = {}              # host_ip → info（含 os_type/host_type 等）

    def load_all_hosts(self) -> int:
        """批量加载在用主机（status=1），构建 host_ip→属性 内存映射，避免逐台调用。

        实测（2026-08）：getInstances 不带 host_ip 条件时一次返回全部主机，
        分页参数被忽略；若生产接口有返回上限，未命中的主机仍走 get() 单条查询兜底。
        """
        result = self._post("getInstances(批量)", self.GET_INSTANCES_API, {
            "ciCode": "host",
            "status": [1],
        })
        if not result or not result.get("data"):
            log(">>> 警告: CMDB 批量加载在用主机返回为空，将逐台查询兜底")
            return 0
        items = result["data"]
        if not isinstance(items, list):
            items = (items.get("records") or []) if isinstance(items, dict) else []

        n = 0
        for item in items:
            cmdb_id = item.get("cmdbId")
            if not cmdb_id:
                continue
            attrs = {}
            for a in item.get("attributes") or []:
                if a.get("attributeCode") is not None:
                    attrs[a["attributeCode"]] = a.get("attributeValue")
            host_ip = attrs.get("host_ip")
            if not host_ip:
                continue
            self._cache.setdefault(host_ip, {
                "cmdbId": cmdb_id,
                "instanceName": item.get("instanceName"),
                "os_type": attrs.get("os_type"),
                "osVendor": attrs.get("osVendor"),
                "host_type": attrs.get("host_type"),
                "host_name": attrs.get("host_name"),
                "environment": attrs.get("environment"),
            })
            n += 1
        log(">>> CMDB 批量加载在用主机 {} 台".format(n))
        return n

    def get(self, host_ip: str):
        if host_ip in self._cache:
            return self._cache[host_ip]

        result = self._post(host_ip, self.GET_INSTANCES_API, {
            "ciCode": "host",
            "status": [1],  # 仅查询在用状态的主机
            "attributeValues": [
                {"attributeCode": "host_ip", "logical": "eq", "attributeValue": host_ip}
            ],
        })

        info = None
        if result and result.get("data"):
            item = result["data"][0]
            attrs = {}
            for a in item.get("attributes") or []:
                if a.get("attributeCode") is not None:
                    attrs[a["attributeCode"]] = a.get("attributeValue")
            info = {
                "cmdbId": item.get("cmdbId"),
                "instanceName": item.get("instanceName"),
                "os_type": attrs.get("os_type"),
                "osVendor": attrs.get("osVendor"),
                "host_type": attrs.get("host_type"),
                "host_name": attrs.get("host_name"),
                "environment": attrs.get("environment"),
            }
        self._cache[host_ip] = info
        return info

    def _post(self, label: str, api: str, data: dict):
        url = self.domain + api
        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "Accept": "*/*",
            "access-key": self.access_key,
        }
        try:
            resp = requests.post(url=url, json=data, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log(">>> CMDB 查询失败 {}: {}".format(label, e))
            return None


def detect_os(cmdb_info: dict):
    """根据 os_type（辅以 osVendor）识别系统类型：windows / linux / None(未知)"""
    if not cmdb_info:
        return None
    t = str(cmdb_info.get("os_type") or "") + " " + str(cmdb_info.get("osVendor") or "")
    t = t.lower()
    if "win" in t:
        return "windows"
    if any(k in t for k in (
        "linux", "redhat", "centos", "ubuntu", "debian", "suse",
        "kylin", "uos", "euleros", "openeuler", "opencloud",
    )):
        return "linux"
    return None


# ==================== 告警策略判断 ====================

def judge(os_kind: str, metrics: dict):
    """返回 (triggered, rule_name, rule_desc)；triggered 为 None 表示无法判断"""
    today_mem = metrics.get("today_mem")
    if today_mem is None:
        return None, None, "当天无内存使用率P95数据，跳过"

    if os_kind == "windows":
        # 策略：内存使用率P95 >= 80% 且 >= 前一天P95 * 110%
        base = metrics.get("baseline_mem")
        if base is None:
            return False, None, "无前一天内存P95基线，跳过"
        if today_mem["p95"] >= WINDOWS_MEM_P95_THRESHOLD \
                and today_mem["p95"] >= base["p95"] * WINDOWS_GROWTH_RATIO:
            desc = "内存P95 {}% >= 80% 且 >= 前一天P95 {}% * 110%".format(
                today_mem["p95"], base["p95"])
            return True, "MEM_P95_WINDOWS_GROWTH", desc
        return False, None, "未达 Windows 策略（P95={}%，基线={}%）".format(
            today_mem["p95"], base["p95"])

    if os_kind == "linux":
        # Linux 策略：按换页开关分两支
        swap_today = metrics.get("swap_today")
        swap_on = (SWAP_CHECK_MODE == "enabled") \
            or (SWAP_CHECK_MODE == "auto" and swap_today is not None)

        if not swap_on:
            # 换页关闭：内存使用率P95 >= 80%
            if today_mem["p95"] >= LINUX_MEM_P95_THRESHOLD:
                desc = "换页关闭：内存P95 {}% >= 80%".format(today_mem["p95"])
                return True, "MEM_P95_LINUX_SWAP_OFF", desc
            return False, None, "未达 Linux 换页关闭策略（P95={}%）".format(today_mem["p95"])
        else:
            # 换页开启：当天换页 >= 前一天换页 * 110%
            swap_base = metrics.get("swap_baseline")
            if swap_today is None or swap_base is None or swap_base["p95"] <= 0:
                return False, None, "无换页数据或换页基线<=0，跳过（换页开启分支）"
            if swap_today["p95"] >= swap_base["p95"] * LINUX_SWAP_GROWTH_RATIO:
                desc = "换页开启：当天换页 {} >= 前一天换页 {} * 110%".format(
                    swap_today["p95"], swap_base["p95"])
                return True, "MEM_P95_LINUX_SWAP_ON", desc
            return False, None, "未达 Linux 换页开启策略（当天={}，基线={}）".format(
                swap_today["p95"], swap_base["p95"])

    return None, None, "未知系统类型 {}".format(os_kind)


# ==================== 告警消息拼装（webhook 字段，平台读取后负责写入 Kafka） ====================

def build_alarm_message(host_ip: str, cmdb_info: dict, metrics: dict,
                        rule_name: str, rule_desc: str, alarm_date: date):
    """拼装 webhook 告警消息。

    字段对照 getTaskStateToKafka.py 的告警接入文档：
    必填: alarmId/triggerId, alarmName, alarmContent, alarmTime, appName,
          metricName, priority, resourceName, status, value
    非必填: cmdbId, metricCode, recoverTime(status=0时必填), tags, unit
    """
    now_ms = int(datetime.now().timestamp() * 1000)
    today = metrics["today_mem"]
    baseline = metrics.get("baseline_mem")
    swap_today = metrics.get("swap_today")
    swap_base = metrics.get("swap_baseline")

    resource = (cmdb_info or {}).get("host_name") or host_ip
    cmdb_id = (cmdb_info or {}).get("cmdbId") or ""
    host_type = (cmdb_info or {}).get("host_type") or ""
    # alarmId 含日期：每天每主机一条独立消息；跨月即下月新消息，无需恢复语义
    alarm_id = "mem_p95_{}_{}".format(host_ip, alarm_date.strftime("%Y%m%d"))

    message = {
        "alarmId": alarm_id,
        "triggerId": TRIGGER_ID,
        "alarmName": "内存使用率P95告警：{}({})，P95={}%".format(
            resource, host_ip, today["p95"]),
        "alarmContent": "主机 {} ({}) 内存使用率P95={}%，触发策略：{}".format(
            resource, host_ip, today["p95"], rule_desc),
        "alarmTime": now_ms,
        "appName": ALARM_APP_NAME,
        "cmdbId": cmdb_id,
        "metricCode": today.get("metricCode") or "",  # ClickHouse 查出的原始 metricCode
        "metricName": MEMORY_CANONICAL,
        "priority": ALARM_PRIORITY,
        "recoverTime": 0,  # 告警消息 status=1；恢复消息(status=0)时才需填
        "resourceName": resource,
        "status": 1,
        "tags": {
            "ip": host_ip,
            "alarmType": "内存使用率P95",
            "rule": rule_name,
            "ruleDesc": rule_desc,
            "osType": (cmdb_info or {}).get("os_type"),
            "hostType": host_type,
            "environment": (cmdb_info or {}).get("environment"),
            "alarmDate": alarm_date.strftime("%Y-%m-%d"),
            "dataWindow": "08:00-16:00",
            "baselineDay": BASELINE_DAY,
            "p95Value": today["p95"],
            "baselineP95": baseline["p95"] if baseline else None,
            "swapTodayP95": swap_today["p95"] if swap_today else None,
            "swapBaselineP95": swap_base["p95"] if swap_base else None,
            "source": "mem_p95_alarm",
        },
        "unit": "%",
        "value": str(today["p95"]),
    }
    return alarm_id, message


# ==================== 入口（参照 host_p95_metric.py：账密在 __main__ 从 PYSCRIPT_SECRETS 读取） ====================

def main():
    parser = argparse.ArgumentParser(description="内存使用率P95告警生成JSON（平台读取后写入Kafka）")
    parser.add_argument("--dry-run", action="store_true", help="试跑，打印命中明细到 stderr，同样输出JSON")
    parser.add_argument("--date", default=None, help="告警日期 YYYY-MM-DD（默认今天）")
    args = parser.parse_args()

    if BASELINE_DAY not in ("today", "prev_workday"):
        fail("BASELINE_DAY 配置非法: {}".format(BASELINE_DAY))

    alarm_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    t_run_start = time.time()

    log(">>> ClickHouse: {}:{}/{}".format(
        clickhouse_auth["host"], clickhouse_auth["port"], clickhouse_auth["database"]))
    log(">>> CMDB: {}".format(cmdb_domain))

    ch = ClickHouseHelper(clickhouse_auth)
    cmdb = CmdbClient(cmdb_domain, cmdb_access_key)

    # 批量加载在用主机到内存（一次请求），避免对每台主机逐次调 CMDB 导致超时
    cmdb.load_all_hosts()

    windows = build_windows(alarm_date)
    log(">>> 采集窗口（08:00-16:00）：")
    for k, w in windows.items():
        log("    {}: {}  [{}, {})".format(k, w["date"], w["start_ms"], w["end_ms"]))

    t0 = time.time()
    data = collect_p95(ch, windows)
    log(">>> collect_p95 耗时 {:.1f}s".format(time.time() - t0))
    mem_today = data.get("memory", {}).get("today", {})
    log(">>> 当天有内存P95数据的主机数: {}".format(len(mem_today)))

    stats = {"windows": 0, "linux": 0, "no_cmdb": 0, "unknown_os": 0, "skipped": 0}
    rule_counts = {}
    messages = []

    for host_ip in sorted(mem_today.keys()):
        cmdb_info = cmdb.get(host_ip)
        if not cmdb_info:
            stats["no_cmdb"] += 1
            log(">>> 跳过 {}: CMDB 无主机信息".format(host_ip))
            continue

        os_kind = detect_os(cmdb_info)
        if os_kind is None:
            stats["unknown_os"] += 1
            log(">>> 跳过 {}: 无法识别系统类型 (os_type={}, osVendor={})".format(
                host_ip, cmdb_info.get("os_type"), cmdb_info.get("osVendor")))
            continue
        stats[os_kind] += 1

        metrics = {
            "today_mem": data.get("memory", {}).get("today", {}).get(host_ip),
            "baseline_mem": data.get("memory", {}).get(BASELINE_DAY, {}).get(host_ip),
            "swap_today": data.get("swap", {}).get("today", {}).get(host_ip),
            "swap_baseline": data.get("swap", {}).get(BASELINE_DAY, {}).get(host_ip),
        }

        triggered, rule_name, desc = judge(os_kind, metrics)
        if triggered is True:
            rule_counts[rule_name] = rule_counts.get(rule_name, 0) + 1
            alarm_id, msg = build_alarm_message(host_ip, cmdb_info, metrics,
                                                rule_name, desc, alarm_date)
            if args.dry_run:
                log(">>> [DRY-RUN] 命中: {} [{}] {}".format(host_ip, rule_name, desc))
                log("    " + json.dumps(msg, ensure_ascii=False))
            messages.append(msg)
        elif triggered is None:
            stats["skipped"] += 1
            log(">>> 跳过 {}: {}".format(host_ip, desc))

    # 汇总跳过原因（不逐台打印，避免刷屏；仅打印数量 + 前5个示例）
    def _excerpt(items, limit=5):
        return items[:limit] if items else []

    if skip_no_cmdb:
        log(">>> 跳过 {} 台: CMDB 无主机信息，示例 {}".format(
            len(skip_no_cmdb), _excerpt(skip_no_cmdb)))
    if skip_unknown_os:
        log(">>> 跳过 {} 台: 无法识别系统类型(os_type为空)，示例 {}".format(
            len(skip_unknown_os), _excerpt(skip_unknown_os)))
    if skip_judge:
        log(">>> 跳过 {} 台: 策略无法判断，示例 {}".format(
            len(skip_judge), _excerpt([(ip, d) for ip, d in skip_judge])))

    # 运行统计输出到 stderr（平台不解析）
    log(">>> 命中告警 {} 条，规则统计: {}".format(len(messages), json.dumps(rule_counts, ensure_ascii=False)))
    log(">>> 统计: {}".format(json.dumps(stats, ensure_ascii=False)))
    log(">>> 总耗时 {:.1f}s".format(time.time() - t_run_start))

    # ---- stdout 只输出告警消息 JSON 数组（平台读取后写入 Kafka；无告警输出 []）----
    # flush=True：防止 stdout 被重定向/管道缓冲、进程被平台超时杀掉时丢失输出
    # 默认单行紧凑（平台解析用）；--pretty 时缩进美化（本地查看用）
    if args.pretty:
        print(json.dumps(messages, ensure_ascii=False, indent=2), flush=True)
    else:
        print(json.dumps(messages, ensure_ascii=False), end="", flush=True)


if __name__ == "__main__":
    # 参照 host_p95_metric.py：PYSCRIPT_SECRETS 明文 JSON 作为账密来源
    raw_secrets = os.environ.get("PYSCRIPT_SECRETS")
    if not raw_secrets:
        fail("缺少环境变量 PYSCRIPT_SECRETS（明文 JSON，需含 clickhouse）。"
             "示例: {\"clickhouse\":{\"host\":\"10.129.134.27\",\"port\":9000,"
             "\"username\":\"default\",\"password\":\"...\",\"database\":\"default\"}}")
    try:
        database_auth = json.loads(raw_secrets.strip())
    except json.JSONDecodeError as e:
        fail("PYSCRIPT_SECRETS 不是合法的明文 JSON: {}".format(e))
    if "clickhouse" not in database_auth:
        fail("PYSCRIPT_SECRETS 缺少 clickhouse 配置")

    clickhouse_auth = database_auth["clickhouse"]

    # CMDB：PYSCRIPT_SECRETS.cmdb → 环境变量 → 默认值
    cmdb_auth = database_auth.get("cmdb") or {}
    cmdb_domain = cmdb_auth.get("domain") or CMDB_DOMAIN
    cmdb_access_key = cmdb_auth.get("accessKey") or CMDB_ACCESS_KEY

    os.environ.setdefault("PYSCRIPT_CH_CONNECT_TIMEOUT", "600")
    os.environ.setdefault("PYSCRIPT_CH_SEND_RECEIVE_TIMEOUT", "1010")
    os.environ.setdefault("PYSCRIPT_CH_MAX_EXECUTION_TIME", "1000")
    os.environ.setdefault("PYSCRIPT_MYSQL_CONNECT_TIMEOUT", "600")
    os.environ.setdefault("PYSCRIPT_MYSQL_READ_TIMEOUT", "")
    os.environ.setdefault("PYSCRIPT_MYSQL_WRITE_TIMEOUT", "")

    main()
