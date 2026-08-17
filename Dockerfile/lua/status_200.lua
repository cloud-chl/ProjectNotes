-- 将所有响应状态码统一改写为 200
-- 注意：只能处理 nginx 已生成响应的情况；上游完全不可达时
--       需要通过 proxy_intercept_errors + error_page 兜底
if ngx.status ~= 200 then
    ngx.status = 200
end
