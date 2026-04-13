#!/bin/bash
# Bird Gallery Web 服务管理脚本
# 用法: ./gallery.sh start|stop|restart|status|logs|healthcheck|ensure|install-agent|uninstall-agent|agent-status

set -euo pipefail

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="$(cd "$PROJECT_ROOT/.." && pwd)"

BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
LOG_DIR="$SCRIPT_DIR/logs"
RUN_DIR="$SCRIPT_DIR/.run"
NGINX_CONF="$WORKSPACE_ROOT/nginx-superpicky.conf"
PYTHON_BIN="$PROJECT_ROOT/venv/bin/python3"
NPM_BIN="$(command -v npm || true)"
NGINX_BIN="$(command -v nginx || true)"

BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
LAUNCH_AGENT_LABEL="com.superpicky.gallery.ensure"
LAUNCH_AGENT_PATH="$HOME/Library/LaunchAgents/${LAUNCH_AGENT_LABEL}.plist"

mkdir -p "$LOG_DIR" "$RUN_DIR"

require_file() {
  local path="$1"
  local label="$2"
  if [[ ! -e "$path" ]]; then
    echo "[错误] 找不到${label}: $path" >&2
    exit 1
  fi
}

is_listening() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

wait_for_port() {
  local port="$1"
  local label="$2"
  local max_attempts="30"
  local attempt="1"

  while (( attempt <= max_attempts )); do
    if is_listening "$port"; then
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done

  echo "[错误] ${label} 未能在预期时间内启动并监听端口 ${port}" >&2
  return 1
}

disable_conflicting_nginx_agents() {
  local uid
  uid="$(id -u)"

  launchctl bootout "gui/${uid}" "$HOME/Library/LaunchAgents/com.photo.nginx.plist" >/dev/null 2>&1 || true
  launchctl disable "gui/${uid}/com.photo.nginx" >/dev/null 2>&1 || true
  launchctl bootout "gui/${uid}" "$HOME/Library/LaunchAgents/homebrew.mxcl.nginx.plist" >/dev/null 2>&1 || true
  launchctl disable "gui/${uid}/homebrew.mxcl.nginx" >/dev/null 2>&1 || true
}

stop_port_processes() {
  local port
  for port in "$@"; do
    local pids
    pids="$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      kill $pids 2>/dev/null || true
      sleep 1
      pids="$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)"
      if [[ -n "$pids" ]]; then
        kill -9 $pids 2>/dev/null || true
      fi
    fi
  done
}

start_backend() {
  echo "[启动] 后端 :8000"
  (
    cd "$BACKEND_DIR"
    nohup env ENV=dev "$PYTHON_BIN" -m uvicorn main:app --host 127.0.0.1 --port 8000 \
      >>"$LOG_DIR/backend.log" 2>>"$LOG_DIR/backend.err" < /dev/null &
    echo $! > "$BACKEND_PID_FILE"
  )
  wait_for_port 8000 "后端"
}

start_frontend() {
  if [[ -z "$NPM_BIN" ]]; then
    echo "[错误] 找不到 npm，请确认 Node.js / npm 已安装" >&2
    exit 1
  fi
  echo "[启动] 前端 :5173"
  (
    cd "$FRONTEND_DIR"
    nohup "$NPM_BIN" run dev -- --host 127.0.0.1 --port 5173 \
      >>"$LOG_DIR/frontend.log" 2>>"$LOG_DIR/frontend.err" < /dev/null &
    echo $! > "$FRONTEND_PID_FILE"
  )
  wait_for_port 5173 "前端"
}

start_nginx() {
  if [[ -z "$NGINX_BIN" ]]; then
    echo "[错误] 找不到 nginx，请确认 Homebrew nginx 已安装" >&2
    exit 1
  fi
  echo "[启动] nginx :80/:443"
  disable_conflicting_nginx_agents
  stop_port_processes 80 443
  "$NGINX_BIN" -c "$NGINX_CONF"
  wait_for_port 80 "nginx"
}

ensure_backend() {
  require_file "$PYTHON_BIN" "Python 解释器"
  if is_listening 8000; then
    echo "[保持] 后端已在运行"
    return 0
  fi
  start_backend
}

ensure_frontend() {
  if is_listening 5173; then
    echo "[保持] 前端已在运行"
    return 0
  fi
  start_frontend
}

ensure_nginx() {
  require_file "$NGINX_CONF" "nginx 配置"
  if is_listening 80 && is_listening 443; then
    echo "[保持] nginx 已在运行"
    return 0
  fi
  start_nginx
}

stop_backend() {
  stop_port_processes 8000
  rm -f "$BACKEND_PID_FILE"
}

stop_frontend() {
  stop_port_processes 5173
  rm -f "$FRONTEND_PID_FILE"
}

stop_nginx() {
  disable_conflicting_nginx_agents
  pkill -9 nginx 2>/dev/null || true
}

show_status() {
  echo "=== nginx (port 80 / 443) ==="
  if is_listening 80; then
    echo "  ✓ 80 已监听"
    lsof -nP -iTCP:80 -sTCP:LISTEN
  else
    echo "  ✗ 80 未监听"
  fi
  if is_listening 443; then
    echo "  ✓ 443 已监听"
    lsof -nP -iTCP:443 -sTCP:LISTEN
  else
    echo "  ✗ 443 未监听"
  fi

  echo ""
  echo "=== 后端 (port 8000) ==="
  if is_listening 8000; then
    echo "  ✓ 运行中"
    lsof -nP -iTCP:8000 -sTCP:LISTEN
  else
    echo "  ✗ 未运行"
  fi

  echo ""
  echo "=== 前端 (port 5173) ==="
  if is_listening 5173; then
    echo "  ✓ 运行中"
    lsof -nP -iTCP:5173 -sTCP:LISTEN
  else
    echo "  ✗ 未运行"
  fi

  echo ""
  run_healthcheck
}

run_healthcheck() {
  local failed=0

  echo "=== 健康检查 ==="

  if is_listening 80; then
    echo "  ✓ nginx 80 端口正常"
  else
    echo "  ✗ nginx 80 端口未监听"
    failed=1
  fi

  if is_listening 443; then
    echo "  ✓ nginx 443 端口正常"
  else
    echo "  ✗ nginx 443 端口未监听"
    failed=1
  fi

  if is_listening 8000; then
    echo "  ✓ 后端 8000 端口正常"
  else
    echo "  ✗ 后端 8000 端口未监听"
    failed=1
  fi

  if is_listening 5173; then
    echo "  ✓ 前端 5173 端口正常"
  else
    echo "  ✗ 前端 5173 端口未监听"
    failed=1
  fi

  if curl -sS -m 5 http://127.0.0.1/ >/dev/null 2>&1; then
    echo "  ✓ 首页 http://127.0.0.1/ 可达"
  else
    echo "  ✗ 首页 http://127.0.0.1/ 不可达"
    failed=1
  fi

  if curl -sS -m 5 http://127.0.0.1/api/batch-process/options >/dev/null 2>&1; then
    echo "  ✓ API http://127.0.0.1/api/batch-process/options 可达"
  else
    echo "  ✗ API http://127.0.0.1/api/batch-process/options 不可达"
    failed=1
  fi

  return "$failed"
}

show_logs() {
  echo "=== 后端日志 (最近 20 行) ==="
  tail -20 "$LOG_DIR/backend.log" 2>/dev/null || true
  echo ""
  echo "=== 后端错误 (最近 20 行) ==="
  tail -20 "$LOG_DIR/backend.err" 2>/dev/null || true
  echo ""
  echo "=== 前端日志 (最近 20 行) ==="
  tail -20 "$LOG_DIR/frontend.log" 2>/dev/null || true
  echo ""
  echo "=== 前端错误 (最近 20 行) ==="
  tail -20 "$LOG_DIR/frontend.err" 2>/dev/null || true
  echo ""
  echo "=== nginx 错误 (最近 20 行) ==="
  tail -20 /tmp/superpicky_nginx_error.log 2>/dev/null || true
}

start_all() {
  require_file "$PYTHON_BIN" "Python 解释器"
  require_file "$NGINX_CONF" "nginx 配置"

  stop_backend
  stop_frontend
  stop_nginx

  start_backend
  start_frontend
  start_nginx

  echo ""
  echo "Bird Gallery Web 已启动。"
  echo "外部设备请继续通过：外部端口 3000 -> 内部端口 80 的映射访问。"
  echo ""
  show_status
}

stop_all() {
  echo "停止 Bird Gallery Web..."
  stop_nginx
  stop_frontend
  stop_backend
  echo "已停止。"
}

ensure_all() {
  echo "检查 Bird Gallery Web 服务..."
  ensure_backend
  ensure_frontend
  ensure_nginx
  echo ""
  show_status
}

write_launch_agent() {
  cat > "$LAUNCH_AGENT_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LAUNCH_AGENT_LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${SCRIPT_DIR}/gallery.sh</string>
    <string>ensure</string>
  </array>

  <key>WorkingDirectory</key>
  <string>${SCRIPT_DIR}</string>

  <key>RunAtLoad</key>
  <true/>

  <key>StartInterval</key>
  <integer>60</integer>

  <key>AbandonProcessGroup</key>
  <true/>

  <key>StandardOutPath</key>
  <string>${LOG_DIR}/launchagent.log</string>

  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/launchagent.err</string>
</dict>
</plist>
EOF
}

install_agent() {
  mkdir -p "$HOME/Library/LaunchAgents"
  write_launch_agent

  local uid
  uid="$(id -u)"

  launchctl bootout "gui/${uid}" "$LAUNCH_AGENT_PATH" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/${uid}" "$LAUNCH_AGENT_PATH"
  launchctl enable "gui/${uid}/${LAUNCH_AGENT_LABEL}" >/dev/null 2>&1 || true

  echo "已安装 LaunchAgent: ${LAUNCH_AGENT_LABEL}"
  echo "配置文件: $LAUNCH_AGENT_PATH"
  echo "行为: 登录时自动执行，并每 60 秒检查一次服务是否需要恢复"
}

uninstall_agent() {
  local uid
  uid="$(id -u)"

  launchctl bootout "gui/${uid}" "$LAUNCH_AGENT_PATH" >/dev/null 2>&1 || true
  launchctl disable "gui/${uid}/${LAUNCH_AGENT_LABEL}" >/dev/null 2>&1 || true
  rm -f "$LAUNCH_AGENT_PATH"

  echo "已卸载 LaunchAgent: ${LAUNCH_AGENT_LABEL}"
}

show_agent_status() {
  local uid
  uid="$(id -u)"

  if [[ ! -f "$LAUNCH_AGENT_PATH" ]]; then
    echo "LaunchAgent 未安装"
    return 0
  fi

  echo "=== LaunchAgent 文件 ==="
  echo "$LAUNCH_AGENT_PATH"
  echo ""
  echo "=== launchctl 状态 ==="
  launchctl print "gui/${uid}/${LAUNCH_AGENT_LABEL}" 2>/dev/null | sed -n '1,80p' || echo "未加载或当前不可见"
}

case "${1:-}" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    sleep 1
    start_all
    ;;
  status)
    show_status
    ;;
  logs)
    show_logs
    ;;
  healthcheck)
    run_healthcheck
    ;;
  ensure)
    ensure_all
    ;;
  install-agent)
    install_agent
    ;;
  uninstall-agent)
    uninstall_agent
    ;;
  agent-status)
    show_agent_status
    ;;
  *)
    echo "用法: $0 {start|stop|restart|status|logs|healthcheck|ensure|install-agent|uninstall-agent|agent-status}"
    exit 1
    ;;
esac
