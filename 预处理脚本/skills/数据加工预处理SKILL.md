---
name: java-processing-preprocess
description: >-
  生成 Java 加工预处理代码，默认使用脚本执行方式（定义非 public 类 + 实例方法，末尾 new 实例化调用）。
  当用户提到以下内容时必须使用此技能：加工预处理、数据预处理、Java 预处理脚本、编写加工规则、
  切割 JSON 数组、清洗 XML 数据、数据格式转换、在加工平台中编写数据处理逻辑。
  也覆盖"类加载执行"模式（{#类名}/{$方法名}模板）作为备选。
  如果用户说"加工预处理"、"预处理脚本"、"写个预处理"、"写个加工处理"、"data preprocessing"，
  此技能必须加载。默认输出脚本执行方式的 Java 代码块。
---

# 加工预处理技能

## 概述

本技能指导你生成 **加工预处理** 的 Java 代码。核心目标是在数据进入下游处理之前，编写 Java 代码对数据进行转换、切割或清洗。

**默认输出方式为脚本执行**——定义非 public 类 + 实例方法，末尾 new 实例化并调用方法。类加载执行为备选模式。

## 脚本执行模式（核心模式）

### 编写规则（重要）

1. **import** 语句放在代码头部，每个导入独占一行
2. **类不加 `public` 修饰**
3. **方法不加 `static`**
4. 编写完方法后，需要 **new 实例化类，然后调用方法**
5. 调用方法时，参数用 **`{&参数名}`** 包裹
6. **仅支持单参数**
7. 返回值直接 `return`

```java
// 脚本执行模板：
import java.util.HashMap;

class Demo {
    public String hello(String word) {
        return word;
    }
}

Demo demo = new Demo();
return demo.hello({&name});
```

## 类加载执行模式（备选）

当用户要求"类加载执行"、"动态编译"、"JDK 原生 API"时使用。

### 模板规则

1. **类名**用 `{#` 和 `}` 包裹 —— `public class {#MyProcessor}`
2. **方法名**用 `{$` 和 `}` 包裹 —— `public static void {$process}(String message)`
3. **禁止 `package` 声明**
4. **类名必须唯一** —— 重复会导致静默覆盖
5. **方法必须为 `public static`，仅支持单参数**

```java
public class {#HelloWorld} {
    public static void {$helloWorld}(String message) {
        System.out.println("Hello, world!");
    }
}
```

## 常用预处理场景

所有场景示例默认使用**脚本执行模式**。

### 场景 1：切割 JSON 数组

**问题**：入站消息的 `data` 字段是一个包含 `alerts` 数组的 JSON 字符串，需要将每个 alert 切割成独立的消息输出。

```java
import com.shsnc.flink.runtime.utils.JsonUtil;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

class SplitMessage {
    public List<String> splitMessage(String message) {
        List<String> results = new ArrayList<>();
        Map map = JsonUtil.jsonToObject(message, Map.class);
        Object data = map.get("data");
        if (data instanceof String) {
            Map mapData = JsonUtil.jsonToObject((String) data, Map.class);
            Object alerts = mapData.get("alerts");
            if (alerts instanceof List) {
                List<Map<String, Object>> dataList = (List) alerts;
                mapData.put("alerts", null);
                for (Map<String, Object> strMap : dataList) {
                    mapData.putAll(strMap);
                    map.put("data", mapData);
                    results.add(JsonUtil.toJsonString(map));
                }
            }
        } else {
            results.add(message);
            return results;
        }
        return results;
    }
}

SplitMessage obj = new SplitMessage();
return obj.splitMessage({&message});
```

### 场景 2：XML 去除签名

**问题**：XML 数据中包含 `{S:...}` 格式的签名块，需要在处理前去除。

```java
import java.util.regex.Pattern;

class RemoveSignature {
    public String removeSignature(String xmlContent) {
        if (xmlContent == null || xmlContent.trim().isEmpty()) {
            return xmlContent;
        }
        return xmlContent.replaceAll("\\{S:[^}]*\\}", "");
    }
}

RemoveSignature obj = new RemoveSignature();
return obj.removeSignature({&xmlContent});
```

### 场景 3：自定义 JSON 字段提取

```java
import com.shsnc.flink.runtime.utils.JsonUtil;
import java.util.HashMap;
import java.util.Map;

class FieldExtractor {
    public String extractFields(String message) {
        Map map = JsonUtil.jsonToObject(message, Map.class);
        Map data = JsonUtil.jsonToObject((String) map.get("data"), Map.class);

        Map<String, Object> result = new HashMap<>();
        result.put("id", data.get("id"));
        result.put("name", data.get("name"));
        result.put("timestamp", data.get("clock"));

        map.put("data", result);
        return JsonUtil.toJsonString(map);
    }
}

FieldExtractor obj = new FieldExtractor();
return obj.extractFields({&message});
```

## JDK API 参考

| API | 用途 |
|-----|------|
| `javax.tools.JavaCompiler` | 动态编译（类加载执行模式使用） |
| `java.util.regex.Pattern` / `String.replaceAll()` | 基于正则的文本清洗 |
| `java.util.ArrayList`, `java.util.HashMap`, `java.util.List`, `java.util.Map` | 数据操作集合 |
| `java.lang.StringBuilder` / `StringBuffer` | 复杂字符串构建 |
| `java.time.*` | 日期/时间解析和格式化 |

注意：JSON 处理示例使用 `com.shsnc.flink.runtime.utils.JsonUtil`（平台工具类）。

## 规则和约束

1. **默认输出脚本执行模式** —— 非 public 类 + 实例方法 + 末尾 new 调用
2. **脚本执行：类不加 `public`，方法不加 `static`，参数用 `{&名称}`**
3. **类加载执行：`{#ClassName}` + `{$methodName}`，`public static`**
4. **禁止 `package` 声明**
5. **仅支持单参数**
6. JSON 操作优先使用 `com.shsnc.flink.runtime.utils.JsonUtil`
7. **始终校验输入** —— 处理前检查 null、空值、非预期类型
8. **异常处理** —— 让异常自然传播或 try-catch 包裹

## 输出格式

**默认输出脚本执行方式的 Java 代码块**，包括：

1. **完整的 Java 代码**（类 + 方法 + 末尾实例化调用）
2. **简要说明**代码作用（1-2 句）
3. **注意事项**

```java
// 输出格式示例（脚本执行）：
import com.shsnc.flink.runtime.utils.JsonUtil;
import java.util.Map;

class ClassName {
    public ReturnType methodName(String message) {
        // 处理逻辑
    }
}

ClassName obj = new ClassName();
return obj.methodName({&message});
```
