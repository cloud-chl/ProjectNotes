import com.shsnc.flink.runtime.utils.JsonUtil;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

class TcpMetricProcessor {
    public List<String> process(String message) {
        List<String> results = new ArrayList<>();

        if (message == null || message.trim().isEmpty()) {
            return results;
        }

        Map root = JsonUtil.jsonToObject(message, Map.class);
        Object headObj = root.get("head");
        Object recordsObj = root.get("records");

        Map head = headObj instanceof Map ? (Map) headObj : new LinkedHashMap();

        if (!(recordsObj instanceof List)) {
            return results;
        }

        List records = (List) recordsObj;
        for (Object recordObj : records) {
            if (!(recordObj instanceof Map)) {
                continue;
            }

            Map record = (Map) recordObj;
            String netlinkName = buildNetlinkName(head, record);

            for (Object keyObj : record.keySet()) {
                String metricName = String.valueOf(keyObj);
                Object value = record.get(metricName);

                if (!(value instanceof Number)) {
                    continue;
                }

                Map metric = new LinkedHashMap();
                metric.put("metricName", metricName);
                metric.put("value", value);
                metric.put("valueType", getValueType(value));
                metric.put("clock", head.get("time"));
                metric.put("netlinkId", head.get("netlinkId"));
                metric.put("tableId", head.get("tableId"));
                metric.put("taskName", head.get("taskName"));
                metric.put("netlinkName", netlinkName);

                results.add(JsonUtil.toJsonString(metric));
            }
        }

        return results;
    }

    private int getValueType(Object value) {
        if (value instanceof Integer || value instanceof Long || value instanceof Short || value instanceof Byte) {
            return 3;
        }
        if (value instanceof Float || value instanceof Double) {
            return 0;
        }
        return 1;
    }

    private String buildNetlinkName(Map head, Map record) {
        String taskName = toStringValue(head.get("taskName"));
        int index = taskName.indexOf("-");
        String netlinkPrefix = index > -1 ? taskName.substring(0, index) : taskName;

        return netlinkPrefix;
    }

    private String toStringValue(Object value) {
        return value == null ? "" : String.valueOf(value);
    }
}

TcpMetricProcessor processor = new TcpMetricProcessor();
return processor.process({&message});