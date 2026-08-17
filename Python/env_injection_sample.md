# host_p95_metricAlarm.py 环境变量注入样例

注入方式（**与 host_p95_metric.py 一致**）：**`PYSCRIPT_SECRETS` 单个明文 JSON 环境变量（必填）**，
含 `clickhouse`（必填）与 `cmdb`（可选，不填用默认值）。

完整可填模板见 `pyscript_secrets.example.json`。

> 说明：
> - 脚本**不直接连 Kafka**。平台任务配置读取脚本 stdout 输出的告警 JSON，由平台负责写入 Kafka
> - 脚本**不依赖 MySQL**：主机 IP 直接取自 ClickHouse 查询结果的 `resourceName` 字段；
>   CMDB 仅用于按 IP 查 os_type / host_type 等属性（判定系统类型）

## 一、PYSCRIPT_SECRETS 的 JSON 结构（完整样例）

```json
{
  "clickhouse": {
    "host": "10.129.134.27",
    "port": 9000,
    "username": "default",
    "password": "你的CK密码",
    "database": "default"
  },
  "cmdb": {
    "domain": "https://ums-test.gf.com.cn",
    "accessKey": "你的CMDB access-key"
  }
}
```

## 二、字段说明

**`clickhouse`（必填，监控指标库，查 `default.metric_dbl`）**

| 字段 | 填什么 | 说明 |
|---|---|---|
| `host` | CK 实例地址 | 如 `10.129.134.27` |
| `port` | **原生 TCP 端口，默认 `9000`** | ⚠️ 不是 HTTP 端口 8123——`clickhouse_driver` 走原生协议 |
| `username` | CK 账号 | 一般 `default` 或专用账号 |
| `password` | CK 密码 | |
| `database` | 库名 | SQL 里写 `default.metric_dbl`，通常填 `default` |

**`cmdb`（可选，主机属性查询；不填则用脚本默认值）**

| 字段 | 填什么 | 说明 |
|---|---|---|
| `domain` | CMDB 域名 | 如 `https://ums-test.gf.com.cn` |
| `accessKey` | CMDB access-key | |

## 三、Linux / CD 平台（bash）注入样例

```bash
# ---- 方式1：内联一次性执行 ----
PYSCRIPT_SECRETS='{"clickhouse":{"host":"10.129.134.27","port":9000,"username":"default","password":"CK_PASSWORD","database":"default"},"cmdb":{"domain":"https://ums-test.gf.com.cn","accessKey":"3550c2efecfc45fca81b76115f620f7f"}}' \
python host_p95_metricAlarm.py --dry-run

# ---- 方式2：先 export 再执行（适合写在调度脚本里） ----
export PYSCRIPT_SECRETS='{"clickhouse":{"host":"10.129.134.27","port":9000,"username":"default","password":"CK_PASSWORD","database":"default"},"cmdb":{"domain":"https://ums-test.gf.com.cn","accessKey":"3550c2efecfc45fca81b76115f620f7f"}}'
python host_p95_metricAlarm.py

# ---- 方式3：crontab 定时任务（cron 环境变量要写在命令里） ----
30 16 * * 1-5 PYSCRIPT_SECRETS='{"clickhouse":{"host":"10.129.134.27","port":9000,"username":"default","password":"CK_PASSWORD","database":"default"},"cmdb":{"domain":"https://ums-test.gf.com.cn","accessKey":"3550c2efecfc45fca81b76115f620f7f"}}' cd /opt/scripts && python host_p95_metricAlarm.py >> /var/log/p95_alarm.log 2>&1

# ---- 方式4：systemd service（EnvironmentFile）----
# /etc/p95-alarm.env:
#   PYSCRIPT_SECRETS={"clickhouse":{"host":"10.129.134.27","port":9000,"username":"default","password":"CK_PASSWORD","database":"default"},"cmdb":{"domain":"https://ums-test.gf.com.cn","accessKey":"3550c2efecfc45fca81b76115f620f7f"}}
# service 里加: EnvironmentFile=/etc/p95-alarm.env
```

## 四、Windows / PowerShell 注入样例

```powershell
# ---- 方式1：一次性（当前进程） ----
$env:PYSCRIPT_SECRETS = '{"clickhouse":{"host":"10.129.134.27","port":9000,"username":"default","password":"CK_PASSWORD","database":"default"},"cmdb":{"domain":"https://ums-test.gf.com.cn","accessKey":"3550c2efecfc45fca81b76115f620f7f"}}'
python host_p95_metricAlarm.py --dry-run   # 试跑
python host_p95_metricAlarm.py             # 正常执行，stdout 输出告警 JSON

# ---- 方式2：Windows 任务计划程序 ----
# 在"操作"里设置"起始于"目录，并在计划任务的环境变量或批处理包装脚本中设置 PYSCRIPT_SECRETS
```

## 五、其他可选环境变量

**ClickHouse 超时（与 host_p95_metric.py 一致，在 `__main__` 中 setdefault）**

| 环境变量 | 说明 | 默认值 |
|---|---|---|
| `PYSCRIPT_CH_CONNECT_TIMEOUT` | CK 连接超时(秒) | `600` |
| `PYSCRIPT_CH_SEND_RECEIVE_TIMEOUT` | CK 收发超时(秒) | `1010` |
| `PYSCRIPT_CH_MAX_EXECUTION_TIME` | CK 最大执行时间(秒) | `1000` |
| `PYSCRIPT_MYSQL_CONNECT_TIMEOUT` | MySQL 连接超时(秒，未使用，保留对齐) | `600` |
| `PYSCRIPT_MYSQL_READ_TIMEOUT` | MySQL 读超时(秒) | 空=不限制 |
| `PYSCRIPT_MYSQL_WRITE_TIMEOUT` | MySQL 写超时(秒) | 空=不限制 |

**CMDB（`PYSCRIPT_SECRETS.cmdb` 未提供时兜底）**

| 环境变量 | 说明 | 示例值 |
|---|---|---|
| `PYSCRIPT_CMDB_DOMAIN` | CMDB 域名 | `https://ums-test.gf.com.cn` |
| `PYSCRIPT_CMDB_ACCESS_KEY` | CMDB access-key | `3550c2efecfc45fca81b76115f620f7f` |

## 六、输出约定（平台对接关键）

- **stdout 只输出最终 JSON**：命中告警时是 webhook 告警消息数组，无告警时输出 `[]`
- **所有运行日志输出到 stderr**，不污染 stdout
- 平台任务配置读取 stdout 的 JSON 后负责写入 Kafka（脚本不连 Kafka）
