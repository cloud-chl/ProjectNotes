# =============================================================================
# 基于 OpenResty 构建支持 Lua 脚本的 Nginx 镜像
# =============================================================================
FROM docker.1ms.run/openresty/openresty:1.31.1.1-bookworm

# ---------------------------------------------------------------------------
# 1. 目录规划
#
#    /opt/nginx/
#    ├── sbin/nginx          nginx 二进制（wrapper）
#    ├── conf/
#    │   ├── nginx.conf      主配置
#    │   └── conf.d/
#    │       ├── *.conf      server 级挂载配置（set / location / rewrite）
#    │       │               ConfigMap shsnc.conf cp 到这里
#    │       └── http/       http 级挂载配置（server / upstream / map 块）
#    ├── logs/               → stdout / stderr
#    ├── modules/            .so 动态模块（含 ngx_http_lua_module）
#    ├── lualib/             Lua 库
#    ├── luajit/             LuaJIT 运行时
#    ├── lua/                用户 Lua 脚本（Volume 挂载）
#    ├── html/               静态文件
#    └── run/                pid + 临时文件
# ---------------------------------------------------------------------------
# OpenResty Debian 包编译时写死了 --http-client-body-temp-path 等临时目录路径
#   指向 /var/run/openresty/，uid 1001 无写权限 → nginx 启动直接炸
#   这里以 root 创建好目录并赋权给 1001，做兜底
RUN mkdir -p /var/run/openresty \
    && chown 1001:0 /var/run/openresty \
    && chmod 775 /var/run/openresty

RUN mkdir -p /opt/nginx/sbin \
    && mkdir -p /opt/nginx/conf/conf.d/http \
    && mkdir -p /opt/nginx/logs \
    && mkdir -p /opt/nginx/modules \
    && mkdir -p /opt/nginx/lualib \
    && mkdir -p /opt/nginx/luajit \
    && mkdir -p /opt/nginx/lua \
    && mkdir -p /opt/nginx/html \
    && mkdir -p /opt/nginx/run/client_body \
    && mkdir -p /opt/nginx/run/fastcgi \
    && mkdir -p /opt/nginx/run/proxy \
    && mkdir -p /opt/nginx/run/scgi \
    && mkdir -p /opt/nginx/run/uwsgi

# ---------------------------------------------------------------------------
# 2. 复制标准配置文件（mime.types / fastcgi_params 等）
# ---------------------------------------------------------------------------
RUN cp /usr/local/openresty/nginx/conf/mime.types      /opt/nginx/conf/ \
    && cp /usr/local/openresty/nginx/conf/fastcgi.conf /opt/nginx/conf/ \
    && cp /usr/local/openresty/nginx/conf/fastcgi_params /opt/nginx/conf/ \
    && cp /usr/local/openresty/nginx/conf/scgi_params  /opt/nginx/conf/ \
    && cp /usr/local/openresty/nginx/conf/uwsgi_params /opt/nginx/conf/ \
    && cp /usr/local/openresty/nginx/conf/koi-utf      /opt/nginx/conf/ \
    && cp /usr/local/openresty/nginx/conf/koi-win      /opt/nginx/conf/ \
    && cp /usr/local/openresty/nginx/conf/win-utf      /opt/nginx/conf/ \
    && cp -r /usr/local/openresty/nginx/html/*         /opt/nginx/html/

# ---------------------------------------------------------------------------
# 3. 动态模块 (.so)
# ---------------------------------------------------------------------------
RUN cp /usr/local/openresty/nginx/modules/*.so /opt/nginx/modules/ 2>/dev/null || true

# ---------------------------------------------------------------------------
# 4. Lua 运行时
# ---------------------------------------------------------------------------
RUN cp -r /usr/local/openresty/luajit      /opt/nginx/luajit \
    && cp -r /usr/local/openresty/lualib/* /opt/nginx/lualib/

# ---------------------------------------------------------------------------
# 5. nginx.conf（与 bitnami nginx.conf 行为对齐 + Lua 支持）
# ---------------------------------------------------------------------------
RUN printf '%s\n' \
    'worker_processes auto;' \
    'error_log /opt/nginx/logs/error.log warn;' \
    'pid /opt/nginx/run/nginx.pid;' \
    '' \
    'events {' \
    '    worker_connections 1024;' \
    '}' \
    '' \
    'http {' \
    '    include /opt/nginx/conf/mime.types;' \
    '    default_type application/octet-stream;' \
    '' \
    '    log_format main '"'"'$remote_addr - $remote_user [$time_local] "$request" '"'" \
    '                    '"'"'$status $body_bytes_sent "$http_referer" '"'" \
    '                    '"'"'"$http_user_agent" "$http_x_forwarded_for"'"'"';' \
    '    access_log /opt/nginx/logs/access.log main;' \
    '    add_header X-Frame-Options SAMEORIGIN;' \
    '' \
    '    sendfile on;' \
    '    tcp_nopush on;' \
    '    tcp_nodelay off;' \
    '    gzip on;' \
    '    gzip_http_version 1.0;' \
    '    gzip_comp_level 2;' \
    '    gzip_proxied any;' \
    '    gzip_types text/plain text/css application/javascript text/xml application/xml+rss;' \
    '    keepalive_timeout 65;' \
    '    server_tokens off;' \
    '' \
    '    # 不把相对路径转成绝对 URL，不拼端口号（对齐 bitnami 行为）' \
    '    absolute_redirect off;' \
    '    port_in_redirect  off;' \
    '    client_max_body_size 80M;' \
    '' \
    '    client_body_temp_path /opt/nginx/run/client_body 1 2;' \
    '    proxy_temp_path       /opt/nginx/run/proxy 1 2;' \
    '    fastcgi_temp_path     /opt/nginx/run/fastcgi 1 2;' \
    '    scgi_temp_path        /opt/nginx/run/scgi 1 2;' \
    '    uwsgi_temp_path       /opt/nginx/run/uwsgi 1 2;' \
    '' \
    '    # -- Lua / OpenResty --' \
    '    lua_package_path  "/opt/nginx/lualib/?.lua;/opt/nginx/lua/?.lua;/usr/local/openresty/lualib/?.lua;;";' \
    '    lua_package_cpath "/opt/nginx/lualib/?.so;/usr/local/openresty/lualib/?.so;;";' \
    '' \
    '    # -- http 级挂载配置（server / upstream / map 块） --' \
    '    include /opt/nginx/conf/conf.d/http/*.conf;' \
    '' \
    '    # -- 默认 server（兜底） --' \
    '    server {' \
    '        listen 8080;' \
    '        listen [::]:8080;' \
    '' \
    '        # -- server 级挂载配置（set / location / rewrite） --' \
    '        include /opt/nginx/conf/conf.d/*.conf;' \
    '' \
    '        location / {' \
    '            default_type text/plain;' \
    '            return 200 "nginx (OpenResty) OK\n";' \
    '        }' \
    '    }' \
    '}' \
    > /opt/nginx/conf/nginx.conf

# ---------------------------------------------------------------------------
# 6. nginx 二进制 wrapper
#    OpenResty 编译 prefix=/usr/local/openresty/nginx，-p 重定向到 /opt/nginx/
# ---------------------------------------------------------------------------
RUN printf '#!/bin/bash\nexec /usr/local/openresty/nginx/sbin/nginx -p /opt/nginx/ "$@"\n' \
    > /opt/nginx/sbin/nginx \
    && chmod +x /opt/nginx/sbin/nginx

# ---------------------------------------------------------------------------
# 7. 日志 → stdout / stderr
# ---------------------------------------------------------------------------
RUN ln -sf /dev/stdout /opt/nginx/logs/access.log \
    && ln -sf /dev/stderr /opt/nginx/logs/error.log

# ---------------------------------------------------------------------------
# 8. 权限
# ---------------------------------------------------------------------------
RUN chown -R 1001:0 /opt/nginx \
    && chmod -R g+rwX /opt/nginx

# ---------------------------------------------------------------------------
# 9. 运行环境
# ---------------------------------------------------------------------------
USER 1001
EXPOSE 8080
WORKDIR /opt/nginx
STOPSIGNAL SIGTERM
ENTRYPOINT []
CMD ["/opt/nginx/sbin/nginx", "-g", "daemon off;"]
