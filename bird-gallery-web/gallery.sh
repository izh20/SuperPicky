#!/bin/bash
# Bird Gallery Web 服务管理脚本
# 用法: ./gallery.sh start|stop|restart|status|logs

BACKEND_LABEL="com.birdgallery.backend"
FRONTEND_LABEL="com.birdgallery.frontend"
LOG_DIR="/Users/zhouheng/claude/SuperPicky/bird-gallery-web/logs"

case "$1" in
  start)
    echo "启动 Bird Gallery..."
    launchctl load ~/Library/LaunchAgents/${BACKEND_LABEL}.plist 2>/dev/null
    launchctl load ~/Library/LaunchAgents/${FRONTEND_LABEL}.plist 2>/dev/null
    sleep 2
    bash "$0" status
    ;;
  stop)
    echo "停止 Bird Gallery..."
    launchctl unload ~/Library/LaunchAgents/${BACKEND_LABEL}.plist 2>/dev/null
    launchctl unload ~/Library/LaunchAgents/${FRONTEND_LABEL}.plist 2>/dev/null
    echo "已停止"
    ;;
  restart)
    bash "$0" stop
    sleep 1
    bash "$0" start
    ;;
  status)
    echo "=== 后端 (port 8000) ==="
    if lsof -nP -i:8000 | grep -q LISTEN; then
      echo "  ✓ 运行中"
      lsof -nP -i:8000 | grep LISTEN
    else
      echo "  ✗ 未运行"
    fi
    echo ""
    echo "=== 前端 (port 5173) ==="
    if lsof -nP -i:5173 | grep -q LISTEN; then
      echo "  ✓ 运行中"
      lsof -nP -i:5173 | grep LISTEN
    else
      echo "  ✗ 未运行"
    fi
    ;;
  logs)
    echo "=== 后端日志 (最近 20 行) ==="
    tail -20 "$LOG_DIR/backend.log" 2>/dev/null
    echo ""
    echo "=== 后端错误 (最近 10 行) ==="
    tail -10 "$LOG_DIR/backend.err" 2>/dev/null
    echo ""
    echo "=== 前端日志 (最近 10 行) ==="
    tail -10 "$LOG_DIR/frontend.log" 2>/dev/null
    ;;
  *)
    echo "用法: $0 {start|stop|restart|status|logs}"
    exit 1
    ;;
esac
