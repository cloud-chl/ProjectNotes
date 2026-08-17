import com.shsnc.flink.runtime.utils.JsonUtil;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

class P95MetricProcessor {
    public List<String> process(String message) {
        List<String> results = new ArrayList<>();

        if (message == null || message.trim().isEmpty()) {
            return results;
        }

        Map root = JsonUtil.jsonToObject(message, Map.class);
        Object dataObj = root.get("data");

        if (!(dataObj instanceof String)) {
            return results;
        }

        String dataStr = ((String) dataObj).trim();
        if (dataStr.isEmpty()) {
            return results;
        }

        List records = JsonUtil.jsonToObject(dataStr, List.class);
        if (records == null) {
            return results;
        }

        for (Object recordObj : records) {
            if (recordObj == null) {
                continue;
            }
            results.add(JsonUtil.toJsonString(recordObj));
        }

        return results;
    }
}

P95MetricProcessor processor = new P95MetricProcessor();
return processor.process({&message});