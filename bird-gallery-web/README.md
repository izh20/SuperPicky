# Bird Gallery Web — 启动指南

## 前置要求

- macOS（Mac Mini M4 或同类 Apple Silicon）
- Python 3.11+（使用项目根目录 `.venv`）
- Node.js 18+
- ffmpeg（`brew install ffmpeg`）
- exiftool（`brew install exiftool`）

## 1. 安装依赖

```bash
# 项目根目录
cd /Users/zhouheng/claude/SuperPicky

# Python 依赖（如已安装可跳过）
source .venv/bin/activate
pip install -r requirements_mac.txt

# 前端依赖
cd bird-gallery-web/frontend
npm install
```

## 2. 启动后端（FastAPI :8000）

```bash
cd /Users/zhouheng/claude/SuperPicky/bird-gallery-web/backend
source ../../.venv/bin/activate

# 开发模式启动（允许 localhost:5173 CORS）
# SCAN_EXTRA_ROOTS 指定允许扫描的额外目录（冒号分隔多个路径）
SCAN_EXTRA_ROOTS="/Users/zhouheng/claude/SuperPicky/only-test" \
ENV=dev \
uvicorn main:app --host 127.0.0.1 --port 8000
```

启动成功后会看到：
```
Bird Gallery Web API ready
INFO:     Uvicorn running on http://127.0.0.1:8000
```

API 文档地址：http://127.0.0.1:8000/docs

## 3. 启动前端（Vite dev server :5173）

新开终端窗口：

```bash
cd /Users/zhouheng/claude/SuperPicky/bird-gallery-web/frontend
npm run dev
```

浏览器访问：**http://localhost:5173**

> Vite 开发服务器已配置 `/api` 代理到 `127.0.0.1:8000`，无需 nginx。

## 4. 测试验证流程

### 4.1 导入照片库

在网页左侧菜单进入 **Dashboard**，使用"扫描目录"功能：

- 扫描路径：`/Users/zhouheng/claude/SuperPicky/only-test/照片`
- 勾选"递归扫描子目录"

或用 API 直接调用：
```bash
curl -X POST http://127.0.0.1:8000/api/library/scan \
  -H "Content-Type: application/json" \
  -d '{"path": "/Users/zhouheng/claude/SuperPicky/only-test/照片", "recursive": true}'
```

### 4.2 浏览照片

进入 **Gallery** 页面查看已导入的照片，可使用筛选面板按鸟种、日期、相机、ISO、光圈等条件过滤。

### 4.3 识别鸟类

- **单张识别**：点击照片进入详情页 → 点击"识别"
- **批量识别**：在 Gallery 勾选多张照片 → 点击"识别选中"

### 4.4 上传视频

进入 **视频** 页面上传视频文件，然后点击"分析"发起 AI 分析任务。

测试视频路径：`/Users/zhouheng/claude/SuperPicky/only-test/视频/` 下的文件。

### 4.5 连拍检测

进入 **连拍** 页面，点击"检测连拍"自动分组。

## 5. 停止服务

- 后端：在终端按 `Ctrl+C`
- 前端：在终端按 `Ctrl+C`

## 5.1 一键管理脚本

如果希望在网站异常时快速恢复整套服务，可直接使用项目自带脚本：

```bash
cd /Users/zhouheng/claude/superpicky/SuperPicky/bird-gallery-web

# 一键启动前端、后端、nginx
./gallery.sh start

# 一键停止整套服务
./gallery.sh stop

# 重启
./gallery.sh restart

# 查看状态
./gallery.sh status

# 仅运行健康检查，失败时返回非 0
./gallery.sh healthcheck

# 查看最近日志
./gallery.sh logs

# 检查缺失服务并自动补拉
./gallery.sh ensure

# 安装开机/登录自动恢复 LaunchAgent
./gallery.sh install-agent

# 查看 LaunchAgent 状态
./gallery.sh agent-status

# 卸载 LaunchAgent
./gallery.sh uninstall-agent
```

说明：

- 该脚本会直接管理 `127.0.0.1:5173`、`127.0.0.1:8000` 和内部 `80/443` 的 nginx。
- 外部设备仍然通过你的端口映射访问，例如：外部 `3000 -> 内部 80`。
- `install-agent` 会在 macOS 登录时自动执行一次 `./gallery.sh ensure`，并且每 60 秒再检查一次是否需要恢复服务。

## 6. 重置数据（可选）

```bash
rm -f /Users/zhouheng/claude/SuperPicky/bird-gallery-web/data/database/gallery.db
```

下次启动后端时会自动重建空数据库。
