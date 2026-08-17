# -*- coding:utf-8 -*-
"""P95 指标查询：ClickHouse 查数据 → MySQL 查 cmdbId 对应的 host_ip → 去重 → 输出 JSON。"""

import os
import json
from datetime import datetime
from clickhouse_driver import Client
import pymysql

def _resolve_timeout(env_var: str, default):
    """读取环境变量中的超时时间（秒）；空值或未设置时返回默认值，None 表示不限制。"""
    if env_var in os.environ and os.environ[env_var] != "":
        return float(os.environ[env_var])
    return default

# CPU、内存指标使用精确匹配
EXACT_METRIC_NAMES = [
    "CPU使用率_zabbix",
    "CPU 整体使用率_zabbix",
    "CPU使用率",
    "物理内存使用率",
    "内存使用率_zabbix",
    "磁盘IO使用率",
]

# 磁盘、分区指标使用模糊匹配
FUZZY_METRIC_NAMES = [
    "磁盘%利用率",
    "% 分区使用率"
]

# 峰值指标：对应数据库中的 mappingMetricName，输出时自动追加 "峰值" 后缀
PEAK_METRIC_NAMES = [
    "CPU使用率_zabbix",
    "CPU 整体使用率_zabbix",
    "CPU使用率",
    "物理内存使用率",
    "内存使用率_zabbix",
    "磁盘IO使用率",
    "磁盘%利用率",
    "% 分区使用率",
]

# 指标名称归一化：变体 + 大小写 → 规范名（P95 和峰值共用）
METRIC_CANONICAL_MAP = {
    "CPU使用率": "CPU使用率",
    "CPU使用率_zabbix": "CPU使用率",
    "CPU 整体使用率_zabbix": "CPU使用率",
    "物理内存使用率": "物理内存使用率",
    "内存使用率_zabbix": "物理内存使用率",
    "磁盘IO使用率": "磁盘IO使用率",
    "磁盘%利用率": "磁盘%利用率",
    "% 分区使用率": "% 分区使用率",
}


SQL_P95 = """
SELECT
    cmdbId,
    metricCode,
    metricName,
    mappingMetricName,
    quantile(0.95)(value) AS p95,
    max(clock) AS max_clock
FROM default.metric_dbl
WHERE _partition_id IN (toString(toYYYYMMDD(today() - 1)), toString(toYYYYMMDD(today())))
  AND clock >= {start_ms}
  AND clock < {end_ms}
  AND startsWith(cmdbId, 'host_')
  AND ({metric_cond})
GROUP BY cmdbId, metricCode, metricName, mappingMetricName
"""

SQL_MAX = """
SELECT
    cmdbId,
    metricCode,
    metricName,
    mappingMetricName,
    max(value) AS max_val,
    max(clock) AS max_clock
FROM default.metric_dbl
WHERE _partition_id IN (toString(toYYYYMMDD(today() - 1)), toString(toYYYYMMDD(today())))
  AND clock >= {start_ms}
  AND clock < {end_ms}
  AND startsWith(cmdbId, 'host_')
  AND ({metric_cond})
GROUP BY cmdbId, metricCode, metricName, mappingMetricName
"""


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

    def query(self, sql: str) -> list[dict]:
        data, col_types = self.client.execute(sql, with_column_types=True)
        columns = [c[0] for c in col_types]
        return [dict(zip(columns, row)) for row in data]


class MySQLHelper:
    """cmdb_id → host_ip 映射查询，带内存缓存"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._cache: dict[str, str] = {}
        self._connect_timeout = _resolve_timeout("PYSCRIPT_MYSQL_CONNECT_TIMEOUT", 10)
        self._read_timeout = _resolve_timeout("PYSCRIPT_MYSQL_READ_TIMEOUT", None)
        self._write_timeout = _resolve_timeout("PYSCRIPT_MYSQL_WRITE_TIMEOUT", None)

    def _get_conn(self):
        return pymysql.connect(
            host=self.cfg["host"],
            port=self.cfg["port"],
            user=self.cfg["username"],
            password=self.cfg["password"],
            database=self.cfg["database"],
            charset="utf8mb4",
            connect_timeout=self._connect_timeout,
            read_timeout=self._read_timeout,
            write_timeout=self._write_timeout,
        )

    def get_host_ip(self, cmdb_id: str) -> str:
        return self._cache.get(cmdb_id, "")

    def batch_load(self, cmdb_ids: list[str], chunk_size: int = 500):
        if not cmdb_ids:
            return
        uncached = [cid for cid in set(cmdb_ids) if cid not in self._cache]
        if not uncached:
            return

        conn = self._get_conn()
        try:
            with conn.cursor() as cursor:
                for i in range(0, len(uncached), chunk_size):
                    chunk = uncached[i:i + chunk_size]
                    placeholders = ", ".join(["%s"] * len(chunk))
                    sql = (
                        "SELECT cmdb_id, instance_name "
                        "FROM cmdb_ci_instance_codeof_host "
                        "WHERE cmdb_id IN (%s)" % placeholders
                    )
                    cursor.execute(sql, chunk)
                    for row in cursor.fetchall():
                        self._cache[row[0]] = row[1]
        finally:
            conn.close()


def build_metric_cond():
    """CPU/内存指标精确匹配，磁盘/分区指标 LIKE 模糊匹配（大小写不敏感）。"""
    conds = []

    # CPU/内存指标：精确匹配
    for name in EXACT_METRIC_NAMES:
        conds.append("lower(mappingMetricName) = '%s'" % name.lower())

    # 磁盘/分区指标：LIKE 模糊匹配
    for name in FUZZY_METRIC_NAMES:
        lower_name = name.lower()
        if "%" in lower_name:
            conds.append("lower(mappingMetricName) LIKE '%s'" % lower_name)
        else:
            conds.append("lower(mappingMetricName) LIKE '%%%s%%'" % lower_name)

    return " OR ".join(conds)


def build_peak_metric_cond():
    """峰值指标匹配条件：大小写不敏感，兼容 cpu使用率 / CPU使用率 等写法。"""
    conds = []
    for name in PEAK_METRIC_NAMES:
        lower_name = name.lower()
        if "%" in lower_name:
            conds.append("lower(mappingMetricName) LIKE '%s'" % lower_name)
        else:
            conds.append("lower(mappingMetricName) = '%s'" % lower_name)
    return " OR ".join(conds)


def query_p95(ch: ClickHouseHelper, start_ms: int, end_ms: int) -> list[dict]:
    sql = SQL_P95.format(
        metric_cond=build_metric_cond(),
        start_ms=start_ms,
        end_ms=end_ms,
    )
    return ch.query(sql)


def query_max(ch: ClickHouseHelper, start_ms: int, end_ms: int) -> list[dict]:
    """查询峰值数据（独立于 P95）。"""
    sql = SQL_MAX.format(
        metric_cond=build_peak_metric_cond(),
        start_ms=start_ms,
        end_ms=end_ms,
    )
    return ch.query(sql)


def deduplicate_records(records: list[dict]) -> list[dict]:
    """同 host 下按优先级去重，只保留一条：
    - CPU: CPU使用率 > CPU使用率_zabbix > CPU 整体使用率_zabbix
    - 内存: 物理内存使用率 > 内存使用率_zabbix
    """
    CPU_PRIORITY_ORDER = [
        "CPU使用率",
        "CPU使用率_zabbix",
        "CPU 整体使用率_zabbix",
    ]
    MEMORY_PRIORITY = {"内存使用率_zabbix": "物理内存使用率"}
    DISK_PRIORITY_HIGH = "磁盘IO使用率"
    DISK_FALLBACK = {"磁盘%利用率"}

    # 排除含"空闲"的指标（如 磁盘0 C:空闲利用率）
    records = [r for r in records if "空闲" not in r.get("mappingMetricName", "")]

    groups: dict[str, list[dict]] = {}
    for r in records:
        groups.setdefault(r["host_ip"], []).append(r)

    result = []
    for host_records in groups.values():
        drop_indices: set[int] = set()

        # CPU 三级优先级去重：找到该 host 最高优先级指标，丢弃其余
        cpu_info: list[tuple[int, int]] = []  # [(index, priority_rank)]
        for i, r in enumerate(host_records):
            name = r.get("mappingMetricName", "")
            if name in CPU_PRIORITY_ORDER:
                cpu_info.append((i, CPU_PRIORITY_ORDER.index(name)))

        if cpu_info:
            best_rank = min(rank for _, rank in cpu_info)
            for i, rank in cpu_info:
                if rank > best_rank:
                    drop_indices.add(i)

        # 内存去重
        for zabbix_key, preferred_key in MEMORY_PRIORITY.items():
            has_preferred = any(
                r.get("mappingMetricName") == preferred_key
                for r in host_records
            )
            if has_preferred:
                for i, r in enumerate(host_records):
                    if r.get("mappingMetricName") == zabbix_key:
                        drop_indices.add(i)

        # 磁盘去重：磁盘IO使用率 优先，存在则丢弃 磁盘%利用率 和 % 分区使用率
        has_io = any(
            r.get("mappingMetricName") == DISK_PRIORITY_HIGH
            for r in host_records
        )
        if has_io:
            for i, r in enumerate(host_records):
                if r.get("mappingMetricName") in DISK_FALLBACK:
                    drop_indices.add(i)

        for i, r in enumerate(host_records):
            if i not in drop_indices:
                result.append(r)

    return result


def build_records(rows: list[dict], mysql_helper: MySQLHelper) -> list[dict]:
    """P95 结果转换：大小写归一 → 去重 → 变体归一。"""
    cmdb_ids = list(set(row["cmdbId"] for row in rows if row["p95"] is not None))
    mysql_helper.batch_load(cmdb_ids)

    records = []
    for row in rows:
        if row["p95"] is None:
            continue
        host_ip = mysql_helper.get_host_ip(row["cmdbId"])
        if not host_ip:
            continue

        # 大小写归一（cpu使用率 → CPU使用率），确保去重逻辑能匹配
        name = _normalize_metric_name(row["metricName"])
        mapping_name = _normalize_metric_name(row["mappingMetricName"])

        records.append({
            "clock": row["max_clock"] // 1000,
            "host_ip": host_ip,
            "metricName": name,
            "mappingMetricName": mapping_name,
            "metricCode": row["metricCode"],
            "value": round(row["p95"], 2),
            "valueType": "0",
        })

    # 去重（基于归一化后名称，复用 CPU/内存/磁盘 优先级规则）
    deduped = deduplicate_records(records)

    # 变体归一（CPU使用率_zabbix → CPU使用率）
    for r in deduped:
        r["mappingMetricName"] = METRIC_CANONICAL_MAP.get(
            r["mappingMetricName"], r["mappingMetricName"]
        )
        r["metricName"] = METRIC_CANONICAL_MAP.get(
            r["metricName"], r["metricName"]
        )

    return deduped


def _normalize_metric_name(name: str) -> str:
    """大小写不敏感匹配规范名（如 cpu使用率 → CPU使用率）。未映射的名称原样返回。"""
    lower_name = name.lower()
    for variant, canonical in METRIC_CANONICAL_MAP.items():
        if variant.lower() == lower_name:
            return canonical
    return name


def build_peak_records(rows: list[dict], mysql_helper: MySQLHelper) -> list[dict]:
    """峰值结果转换：大小写归一 → 去重 → 变体归一 → 追加 "峰值" 后缀。"""
    cmdb_ids = list(set(row["cmdbId"] for row in rows if row["max_val"] is not None))
    mysql_helper.batch_load(cmdb_ids)

    records = []
    for row in rows:
        if row["max_val"] is None:
            continue
        host_ip = mysql_helper.get_host_ip(row["cmdbId"])
        if not host_ip:
            continue

        # 大小写归一（cpu使用率 → CPU使用率），确保去重逻辑能匹配
        name = _normalize_metric_name(row["metricName"])
        mapping_name = _normalize_metric_name(row["mappingMetricName"])

        records.append({
            "clock": row["max_clock"] // 1000,
            "host_ip": host_ip,
            "metricName": name,
            "mappingMetricName": mapping_name,
            "metricCode": row["metricCode"],
            "value": round(row["max_val"], 2),
            "valueType": "1",
        })

    # 去重（基于归一化后名称，复用 CPU/内存/磁盘 优先级规则）
    deduped = deduplicate_records(records)

    # 变体归一 + 追加 "峰值" 后缀
    for r in deduped:
        r["mappingMetricName"] = METRIC_CANONICAL_MAP.get(
            r["mappingMetricName"], r["mappingMetricName"]
        ) + "峰值"
        r["metricName"] = METRIC_CANONICAL_MAP.get(
            r["metricName"], r["metricName"]
        ) + "峰值"

    return deduped


def main():
    # 脚本 16:00 执行，采集窗口：当天 08:00 → 16:00（仅采集工作时段数据）
    now = datetime.now()
    today_8 = now.replace(hour=8, minute=0, second=0, microsecond=0)
    today_16 = now.replace(hour=16, minute=0, second=0, microsecond=0)

    start_ms = int(today_8.timestamp() * 1000)
    end_ms = int(today_16.timestamp() * 1000)

    ch = ClickHouseHelper(clickhouse_auth)
    mysql = MySQLHelper(mysql_auth)

    # P95 查询
    p95_rows = query_p95(ch, start_ms, end_ms)
    p95_records = build_records(p95_rows, mysql)

    # 峰值查询（独立）
    max_rows = query_max(ch, start_ms, end_ms)
    max_records = build_peak_records(max_rows, mysql)

    # 合并输出
    all_records = p95_records + max_records
    print(json.dumps(all_records, ensure_ascii=False), end="")


if __name__ == "__main__":
    database_auth = json.loads(os.environ['PYSCRIPT_SECRETS'])
    clickhouse_auth = database_auth["clickhouse"]
    mysql_auth = database_auth["mysql"]

    os.environ.setdefault("PYSCRIPT_CH_CONNECT_TIMEOUT", "600")
    os.environ.setdefault("PYSCRIPT_CH_SEND_RECEIVE_TIMEOUT", "1010")
    os.environ.setdefault("PYSCRIPT_CH_MAX_EXECUTION_TIME", "1000")
    os.environ.setdefault("PYSCRIPT_MYSQL_CONNECT_TIMEOUT", "600")
    os.environ.setdefault("PYSCRIPT_MYSQL_READ_TIMEOUT", "")
    os.environ.setdefault("PYSCRIPT_MYSQL_WRITE_TIMEOUT", "")

    main()
