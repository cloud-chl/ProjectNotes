import com.shsnc.flink.runtime.utils.JsonUtil;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * TCP 会话数据转换预处理脚本（脚本执行模式）。
 *
 * 输入: 加工平台包装的 JSON，data 字段为 TCP_FLOW 数组
 * 输出: List<String>，每条一个转换后的 JSON，格式对齐 temp2.json
 */
class TcpFlowConverter {
    private static final SimpleDateFormat SDF = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");

    public List<String> process(String message) {
        if (message == null || message.isEmpty()) {
            return new ArrayList<>();
        }

        // 1. 解析外层包装
        Map root = JsonUtil.jsonToObject(message, Map.class);
        Object dataObj = root.get("data");
        if (dataObj == null) {
            return new ArrayList<>();
        }

        // 2. 解析 data 字段：兼容 String 和已解析的 List
        List records;
        if (dataObj instanceof String) {
            records = JsonUtil.jsonToObject((String) dataObj, List.class);
        } else if (dataObj instanceof List) {
            records = (List) dataObj;
        } else {
            return new ArrayList<>();
        }
        if (records == null || records.isEmpty()) {
            return new ArrayList<>();
        }

        // 3. 提取外层常量
        String dataSourceCode = root.get("dataSourceCode") != null
                ? String.valueOf(root.get("dataSourceCode")) : null;
        long kafkaInputTime = toLong(root.get("finishTime"));

        List<String> results = new ArrayList<>(records.size());
        int flowIndex = 0;

        for (Object recordObj : records) {
            if (!(recordObj instanceof Map)) {
                continue;
            }
            Map record = (Map) recordObj;
            flowIndex++;

            // 4. 构建输出 Map（LinkedHashMap 保持字段顺序）
            Map output = new LinkedHashMap();

            // 时间字段：字符串 → epoch 毫秒
            output.put("flow_start_time", parseTime(String.valueOf(record.get("flow_start_time"))));
            output.put("flow_end_time",   parseTime(String.valueOf(record.get("flow_end_time"))));
            output.put("first_seen_time", parseTime(String.valueOf(record.get("first_seen_time"))));
            output.put("last_seen_time",  parseTime(String.valueOf(record.get("last_seen_time"))));
            output.put("last_sync_time",  parseTime(String.valueOf(record.get("last_sync_time"))));
            output.put("last_update",     parseTime(String.valueOf(record.get("flow_end_time"))));

            // flow_id（原名 id）
            String flowId = String.valueOf(record.get("id"));
            output.put("flow_id", flowId);

            // server_port 从 flow_id 末尾提取（格式: xxx_IP_IP_PORT）
            String portFromId = extractPort(flowId);

            // IP / 端口 / 时长（全部转字符串）
            output.put("client_ip_addr", String.valueOf(record.get("client_ip_addr")));
            output.put("server_ip_addr", String.valueOf(record.get("server_ip_addr")));
            output.put("server_port",    portFromId);
            output.put("flow_duration",  String.valueOf(record.get("flow_duration")));

            // 来源元数据
            output.put("sourceDataCode", "cola_tcpflow");
            if (dataSourceCode != null && !"null".equals(dataSourceCode)) {
                output.put("dataSourceCode", dataSourceCode);
            } else {
                output.put("dataSourceCode", null);
            }
            output.put("kafkaInputTime", kafkaInputTime);

            // tags
            Map tags = new HashMap();
            tags.put("flowId", flowIndex);
            output.put("tags", tags);

            // 嵌套数组：CLIENT_APP / SERVER_APP 保留全部字段
            output.put("CLIENT_APP",  record.get("CLIENT_APP"));
            output.put("SERVER_APP",  record.get("SERVER_APP"));
            output.put("HOST",  record.get("HOST"));
            output.put("LINE",  record.get("LINE"));

            // 5. 用平台 JsonUtil 序列化为 JSON 字符串
            results.add(JsonUtil.toJsonString(output));
        }

        return results;
    }

    /**
     * 将 "yyyy-MM-dd HH:mm:ss" 格式字符串转为 epoch 毫秒。
     */
    private long parseTime(String timeStr) {
        if (timeStr == null || timeStr.isEmpty() || "null".equals(timeStr)) {
            return 0L;
        }
        try {
            return SDF.parse(timeStr).getTime();
        } catch (Exception e) {
            return 0L;
        }
    }

/**
     * 从 flow_id 末尾提取端口号（格式: xxx_IP_IP_PORT）。
     */
    private String extractPort(String flowId) {
        if (flowId == null || flowId.isEmpty()) {
            return "";
        }
        int idx = flowId.lastIndexOf('_');
        if (idx > -1 && idx < flowId.length() - 1) {
            return flowId.substring(idx + 1);
        }
        return "";
    }

    private long toLong(Object obj) {
        if (obj instanceof Number) {
            return ((Number) obj).longValue();
        }
        if (obj instanceof String) {
            try {
                return Long.parseLong((String) obj);
            } catch (NumberFormatException e) {
                return 0L;
            }
        }
        return 0L;
    }
}

TcpFlowConverter converter = new TcpFlowConverter();
return converter.process({&message});
