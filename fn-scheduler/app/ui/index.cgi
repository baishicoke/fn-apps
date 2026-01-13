#!/bin/bash

# 脚本名称: index.cgi
#   版本: 1.0.0
#   作者: FNOSP/xieguanru
#   协作者: FNOSP/MR_XIAOBO
# 创建日期: 2025-11-18
# 最后修改: 2025-11-19
#   描述: 这个脚本用于演示Shell脚本的各种注释方式
# 使用方式: 文件重命名, 从linux_shell_cgi_index.sh改成index.cgi,
#          放置应用包/ui路径下, 记得 chmod +x index.cgi 赋权
#   许可证: MIT

# 【注意】修改你自己的静态文件根目录，以本应用为例：
BASE_PATH="/var/apps/fn-scheduler/target/www"

# 1. 从 REQUEST_URI 里拿到 index.cgi 后面的路径
#    例如：/cgi/ThirdParty/fn-scheduler/index.cgi/index.html?foo=bar
#    先去掉 ? 后面的 query string
URI_NO_QUERY="${REQUEST_URI%%\?*}"

# 默认值 (如果没匹配到 index.cgi)
REL_PATH="/"

# 用 index.cgi 作为切割点，取后面的部分
case "$URI_NO_QUERY" in
  *index.cgi*)
    # 去掉前面所有直到 index.cgi 为止的内容，保留后面的
    # /cgi/ThirdParty/fn-scheduler/index.cgi/index.html -> /index.html
    REL_PATH="${URI_NO_QUERY#*index.cgi}"
    ;;
esac

# 如果为空或只有 /，就默认 /index.html
if [ -z "$REL_PATH" ] || [ "$REL_PATH" = "/" ]; then
  REL_PATH="/index.html"
fi

# 如果是后端 API 请求，代理到后端（支持 UNIX socket 或 TCP）
if [[ "$REL_PATH" == /api* ]]; then
  # Prefer explicit BACKEND_UNIX_SOCKET, else SCHEDULER_UNIX_SOCKET, else common install path
  BACKEND_UNIX_SOCKET="${BACKEND_UNIX_SOCKET:-${SCHEDULER_UNIX_SOCKET:-/usr/local/apps/@appdata/fn-scheduler/scheduler.sock}}"
  BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
  BACKEND_PORT="${BACKEND_PORT:-28256}"

  if [ -n "$CONTENT_LENGTH" ] && [ "$CONTENT_LENGTH" -gt 0 ] 2>/dev/null; then
    BODY_TMP=$(mktemp)
    dd bs=1 count="$CONTENT_LENGTH" of="$BODY_TMP" 2>/dev/null || cat > "$BODY_TMP"
  else
    BODY_TMP=$(mktemp)
    : > "$BODY_TMP"
  fi

  HDR_TMP=$(mktemp)
  OUT_BODY=$(mktemp)

  curl_args=( -sS -D "$HDR_TMP" -o "$OUT_BODY" -X "$REQUEST_METHOD" )
  if [ -n "$CONTENT_TYPE" ]; then
    curl_args+=( -H "Content-Type: $CONTENT_TYPE" )
  fi
  # forward Authorization headers if present
  if [ -n "$HTTP_AUTHORIZATION" ]; then
    curl_args+=( -H "Authorization: $HTTP_AUTHORIZATION" )
  elif [ -n "$REDIRECT_HTTP_AUTHORIZATION" ]; then
    curl_args+=( -H "Authorization: $REDIRECT_HTTP_AUTHORIZATION" )
  fi

  case "$REQUEST_METHOD" in
    POST|PUT|PATCH)
      curl_args+=( --data-binary "@$BODY_TMP" )
      ;;
  esac

  if [ -n "$BACKEND_UNIX_SOCKET" ]; then
    BACKEND_URL="http://localhost${REL_PATH}"
    curl --unix-socket "$BACKEND_UNIX_SOCKET" "${curl_args[@]}" "$BACKEND_URL"
  else
    BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}${REL_PATH}"
    curl "${curl_args[@]}" "$BACKEND_URL"
  fi

  status_line=$(head -n1 "$HDR_TMP" 2>/dev/null || echo "HTTP/1.1 502 Bad Gateway")
  status_code=$(echo "$status_line" | awk '{print $2}' 2>/dev/null || echo "502")
  resp_ct=$(grep -i '^Content-Type:' "$HDR_TMP" | head -n1 | sed -e 's/^[Cc]ontent-[Tt]ype:[[:space:]]*//' )
  if [ -z "$resp_ct" ]; then
    resp_ct="application/octet-stream"
  fi

  echo "Status: $status_code"
  echo "Content-Type: $resp_ct"
  echo ""
  cat "$OUT_BODY"

  rm -f "$HDR_TMP" "$BODY_TMP" "$OUT_BODY"
  exit 0
fi

# 拼出真实文件路径: BASE_PATH + /ui + index.cgi 后面的路径
TARGET_FILE="${BASE_PATH}${REL_PATH}"

# 简单防御：禁止 .. 越级访问
if echo "$TARGET_FILE" | grep -q '\.\.'; then
  echo "Status: 400 Bad Request"
  echo "Content-Type: text/plain; charset=utf-8"
  echo ""
  echo "Bad Request"
  exit 0
fi

# 2. 判断文件是否存在
if [ ! -f "$TARGET_FILE" ]; then
  echo "Status: 404 Not Found"
  echo "Content-Type: text/plain; charset=utf-8"
  echo ""
  echo "404 Not Found: ${REL_PATH}"
  exit 0
fi

# 3. 根据扩展名简单判断 Content-Type
ext="${TARGET_FILE##*.}"
case "$ext" in
  html | htm)
    mime="text/html; charset=utf-8"
    ;;
  css)
    mime="text/css; charset=utf-8"
    ;;
  js)
    mime="application/javascript; charset=utf-8"
    ;;
  cgi)
    mime="application/x-httpd-cgi"
    ;;
  jpg | jpeg)
    mime="image/jpeg"
    ;;
  png)
    mime="image/png"
    ;;
  gif)
    mime="image/gif"
    ;;
  svg)
    mime="image/svg+xml"
    ;;
  txt | log)
    mime="text/plain; charset=utf-8"
    ;;
  *)
    mime="application/octet-stream"
    ;;
esac

# 4. 输出头 + 文件内容
echo "Content-Type: $mime"
echo ""

cat "$TARGET_FILE"
