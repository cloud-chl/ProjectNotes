import com.shsnc.flink.runtime.utils.JsonUtil;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

class TcpMetricProcessor {
    public List<String> process(String message) {
        // 1. 快速空值判断，避免 trim() 创建新 String
        if (message == null || message.isEmpty()) {
            return new ArrayList<>();
        }

        Map root = JsonUtil.jsonToObject(message, Map.class);
        Object headObj = root.get("head");
        Object recordsObj = root.get("records");

        if (!(headObj instanceof Map) || !(recordsObj instanceof List)) {
            return new ArrayList<>();
        }

        Map head = (Map) headObj;

        // 2. 【核心优化】提取 head 常量字段，避免在内层循环中重复 get（每条 metric 省 5 次 Map 查找）
        String clock     = String.valueOf(head.get("time"));
        String netlinkId = String.valueOf(head.get("netlinkId"));
        String serverIp  = String.valueOf(head.get("serverIp"));
        String tableId   = String.valueOf(head.get("tableId"));
        String taskName  = String.valueOf(head.get("taskName"));

        // 3. 预计算 netlinkPrefix，所有 record 共用（省去每个 record 的 indexOf + substring）
        int idx = taskName.indexOf('-');
        String netlinkPrefix = idx > -1 ? taskName.substring(0, idx) : taskName;

        List records = (List) recordsObj;
        // 4. 预估容量，减少 ArrayList 扩容次数
        List<String> results = new ArrayList<>(records.size() * 4);

        for (Object recordObj : records) {
            if (!(recordObj instanceof Map)) {
                continue;
            }

            Map record = (Map) recordObj;

            // 5. StringBuilder 替代 String + 拼接，减少中间对象
            String netlinkName = new StringBuilder(128)
                .append(netlinkPrefix).append('_')
                .append(toStringValue(record.get("client_ip_addr"))).append('_')
                .append(toStringValue(record.get("server_ip_addr"))).append('_')
                .append(toStringValue(record.get("server_port")))
                .toString();

            // 6. 【核心优化】entrySet() 遍历替代 keySet() + get()，每次迭代省 1 次 Map 查找
            for (Object entryObj : record.entrySet()) {
                Map.Entry entry = (Map.Entry) entryObj;
                Object value = entry.getValue();

                if (!(value instanceof Number)) {
                    continue;
                }

                String metricName = String.valueOf(entry.getKey());

                // 7. 【核心优化】手动拼装 JSON，避免每条 metric 创建 HashMap + JsonUtil 反射序列化
                String json = new StringBuilder(256)
                    .append("{\"metricName\":\"").append(escapeJson(metricName))
                    .append("\",\"value\":").append(value)
                    .append(",\"valueType\":").append(getValueType(value))
                    .append(",\"clock\":\"").append(escapeJson(clock))
                    .append("\",\"netlinkId\":\"").append(escapeJson(netlinkId))
                    .append("\",\"serverIp\":\"").append(escapeJson(serverIp))
                    .append("\",\"tableId\":\"").append(escapeJson(tableId))
                    .append("\",\"taskName\":\"").append(escapeJson(taskName))
                    .append("\",\"netlinkName\":\"").append(escapeJson(netlinkName))
                    .append("\"}")
                    .toString();

                results.add(json);
            }
        }

        return results;
    }

    // 8. 按实际数据频次排序 instanceof 分支（Long/Double 在 JSON 反序列化中最常见）
    private int getValueType(Object value) {
        if (value instanceof Long)    return 3;
        if (value instanceof Integer) return 3;
        if (value instanceof Double)  return 0;
        if (value instanceof Float)   return 0;
        if (value instanceof Short || value instanceof Byte) return 3;
        return 1;
    }

    private String toStringValue(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    /**
     * JSON 字符串转义：快速路径，大多数数据无需转义直接返回
     */
    private String escapeJson(String s) {
        if (s == null || s.isEmpty()) {
            return "";
        }
        int n = s.length();
        // 快速路径：先扫描是否包含需要转义的字符
        for (int i = 0; i < n; i++) {
            char c = s.charAt(i);
            if (c == '"' || c == '\\' || c < 0x20) {
                // 命中才走完整转义逻辑
                StringBuilder sb = new StringBuilder(n + 16);
                sb.append(s, 0, i);
                for (int j = i; j < n; j++) {
                    char ch = s.charAt(j);
                    switch (ch) {
                        case '"':  sb.append("\\\""); break;
                        case '\\': sb.append("\\\\"); break;
                        case '\n': sb.append("\\n");  break;
                        case '\r': sb.append("\\r");  break;
                        case '\t': sb.append("\\t");  break;
                        case '\b': sb.append("\\b");  break;
                        case '\f': sb.append("\\f");  break;
                        default:
                            if (ch < 0x20) {
                                sb.append("\\u");
                                String hex = Integer.toHexString(ch);
                                for (int k = hex.length(); k < 4; k++) sb.append('0');
                                sb.append(hex);
                            } else {
                                sb.append(ch);
                            }
                    }
                }
                return sb.toString();
            }
        }
        return s; // 无需转义，直接返回
    }
}

TcpMetricProcessor processor = new TcpMetricProcessor();
return processor.process({&message});
