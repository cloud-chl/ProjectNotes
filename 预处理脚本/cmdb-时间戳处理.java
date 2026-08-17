import com.shsnc.flink.runtime.utils.JsonUtil;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

class TcpFlowDateToTimestamp {
    // 匹配 yyyy-MM-dd HH:mm:ss 格式的日期字符串
    private static final Pattern DATE_PATTERN =
            Pattern.compile("\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}");

    private static final DateTimeFormatter FORMATTER =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    // 中国时区（UTC+8），与数据中的时间一致
    private static final ZoneId ZONE = ZoneId.of("Asia/Shanghai");

    public String convert(String message) {
        // 空值校验
        if (message == null || message.isEmpty()) {
            return message;
        }

        Map<String, Object> map = JsonUtil.jsonToObject(message, Map.class);

        // 只处理 _object_id 为 TCP_FLOW 的数据
        Object objectId = map.get("_object_id");
        if (!"TCP_FLOW".equals(objectId)) {
            return message;
        }

        // 1. 提取值为数组（List）的字段到 relation 中，并从顶层移除
        Map<String, Object> relation = new HashMap<>();
        Iterator<Map.Entry<String, Object>> it = map.entrySet().iterator();
        while (it.hasNext()) {
            Map.Entry<String, Object> entry = it.next();
            if (entry.getValue() instanceof List) {
                relation.put(entry.getKey(), entry.getValue());
                it.remove();
            }
        }
        if (!relation.isEmpty()) {
            map.put("relation", relation);
        }

        // 2. 遍历剩余字段，将日期格式的字符串转为 13 位毫秒时间戳
        for (Map.Entry<String, Object> entry : map.entrySet()) {
            Object value = entry.getValue();
            if (value instanceof String) {
                String strValue = (String) value;
                if (DATE_PATTERN.matcher(strValue).matches()) {
                    try {
                        LocalDateTime ldt = LocalDateTime.parse(strValue, FORMATTER);
                        long timestamp = ldt.atZone(ZONE).toInstant().toEpochMilli();
                        entry.setValue(timestamp);
                    } catch (Exception e) {
                        // 解析失败则保留原值，继续处理下一个字段
                    }
                }
            }
        }

        return JsonUtil.toJsonString(map);
    }
}

TcpFlowDateToTimestamp processor = new TcpFlowDateToTimestamp();
return processor.convert({&message});
