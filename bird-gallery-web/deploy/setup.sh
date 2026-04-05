#!/bin/bash
# Bird Gallery Web 一键部署脚本（macOS）
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

echo "=== Bird Gallery Web Setup ==="

# 1. 创建数据目录
echo "[1/6] Creating data directories..."
mkdir -p "$PROJECT_DIR/data/database" \
         "$PROJECT_DIR/data/thumbnails" \
         "$PROJECT_DIR/data/videos/original" \
         "$PROJECT_DIR/data/videos/transcoded" \
         "$PROJECT_DIR/data/videos/burst" \
         "$PROJECT_DIR/data/frames" \
         "$PROJECT_DIR/data/gallery/by_bird" \
         "$PROJECT_DIR/data/uploads/photos"

# 2. Python 虚拟环境
echo "[2/6] Setting up Python virtual environment..."
if [ ! -d "$BACKEND_DIR/.venv" ]; then
    python3 -m venv "$BACKEND_DIR/.venv"
fi
source "$BACKEND_DIR/.venv/bin/activate"
pip install -r "$BACKEND_DIR/requirements.txt"

# 3. 验证后端
echo "[3/6] Verifying Python files..."
for f in "$BACKEND_DIR"/*.py "$BACKEND_DIR"/api/*.py "$BACKEND_DIR"/services/*.py "$BACKEND_DIR"/models/*.py; do
    if [ -f "$f" ]; then
        python3 -m py_compile "$f"
        echo "  ✓ $(basename "$f")"
    fi
done

# 4. 构建前端
echo "[4/6] Building Vue3 frontend..."
if command -v node &>/dev/null; then
    cd "$FRONTEND_DIR"
    npm install
    npm run build
    echo "  ✓ Frontend built → frontend/dist/"
    cd "$PROJECT_DIR"
else
    echo "  ⚠ Node.js not found. Install: brew install node"
fi

# 5. nginx 配置
echo "[5/6] Configuring nginx..."
if command -v nginx &>/dev/null; then
    echo "  nginx is installed"
    echo "  Copy config: sudo cp $SCRIPT_DIR/nginx.conf /opt/homebrew/etc/nginx/servers/birdgallery.conf"
    echo "  Test: sudo nginx -t"
    echo "  Restart: sudo brew services restart nginx"
else
    echo "  ⚠ nginx not found. Install: brew install nginx"
fi

# 6. 提示
echo "[6/6] Setup complete!"
echo ""
echo "To start the API server:"
echo "  cd $BACKEND_DIR"
echo "  source .venv/bin/activate"
echo "  ENV=dev uvicorn main:app --host 127.0.0.1 --port 8000 --reload"
echo ""
echo "  For development (separate frontend dev server):"
echo "  cd $FRONTEND_DIR && npm run dev   # runs on :5173, proxies /api → :8000"
echo ""
echo "To create htpasswd users:"
echo "  htpasswd -c /opt/homebrew/etc/nginx/.htpasswd username"
echo ""
echo "To register launchd service:"
echo "  cp $SCRIPT_DIR/com.birdgallery.api.plist ~/Library/LaunchAgents/"
echo "  launchctl load ~/Library/LaunchAgents/com.birdgallery.api.plist"
