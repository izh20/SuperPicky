---
description: "Use when developing bird-gallery-web FastAPI backend, Vue3 frontend, nginx config, SQLite schema, AI model management, chunked upload, or burst photo features in bird-gallery-web/"
applyTo: "bird-gallery-web/**"
---

# Bird Gallery Web 开发规则

## 核心规则

- **UTF-8 安全**：鸟种中文名贯穿 DB/API/前端/EXIF 全链路，任何环节不得产生乱码。
- **ExifTool 非 ASCII 写入**：必须用 UTF-8 临时文件重定向（`-Tag<=file`），复用 `tools/exiftool_manager.py`。
- **SQLite 多线程安全**：FastAPI BackgroundTasks 与主线程并发读写 `gallery.db`，必须用 WAL 模式 + 每请求从连接池获取连接（依赖注入 `get_db()`），禁止在 BackgroundTasks 中共享同一连接。
- **不绕过 DB 封装**：所有数据库操作通过 `models/database.py`，不直接操作底层连接。
- **事务防御性**：分块上传合并、批量识别写入等多步操作，确保原子性和失败回滚。
- **持久化进程关闭**：FastAPI shutdown 事件中必须调用 `ExifToolManager.close()` 和 `ModelManager` 清理；daemon 线程用 `threading.Event` 的 `set()` + `join(timeout=5)` 优雅退出。

## 不适用的父项目规则

- ~~Windows 兼容性~~：仅 macOS 部署，可用 `os.symlink`、`launchd`、MPS。
- ~~CUDA/PyInstaller 打包~~：不使用 CUDA，不打包。
- ~~`py -3`~~：macOS 用 `python3 -m py_compile`。
- **例外**：修改 `core/`、`tools/`、`birdid/` 共享模块时仍须保持 Windows 兼容。

## 架构约束

- FastAPI `:8000`，不得干扰 Flask `:5156`。
- `sys.path.insert` 复用根目录模块，必须在所有 import 之前执行，放 `backend/main.py` 顶部。
- 单 Uvicorn worker + `asyncio.Lock` 串行化 MPS 推理。

## AI 模型管理

- `ModelManager` 按需加载，TTL 5 分钟自动释放。
- 释放调用 `torch.mps.empty_cache()` + `gc.collect()`。
- YOLO 可常驻（~150MB），OSEA/Keypoint/TOPIQ 走 LRU。

## 文件安全

- 上传白名单：MIME + 扩展名双重校验。
- 路径参数（`scan_path`）：目录白名单校验，防路径穿越。
- 文件名清洗：去除 `../`、`/`、`\` 及特殊字符。

## 大文件上传

- 单文件 ≤10GB，文件夹 ≤50GB，10MB/块分块上传。
- nginx: `proxy_request_buffering off` + `client_max_body_size 10G` + `proxy_read_timeout 1800s`。

## 前端

- Vue 3 + Vite，nginx 直接提供 `dist/` 静态文件。
- 大量照片用 `vue-virtual-scroller` 虚拟滚动。

## CORS

- 生产：仅允许 DDNS 域名，禁止 `*`。
- 开发：额外允许 `http://localhost:5173`，通过 `ENV=dev` 环境变量控制。

## 验证清单

- `python3 -m py_compile` 检查修改的 Python 文件。
- EXIF 中文写入后读取回显验证。
- DB schema 变更后多线程读写压力测试。
- nginx 配置变更后 `nginx -t` 语法检查。
- 模型生命周期变更后验证 TTL 释放和 `/api/admin/metrics` 内存下降。
- 分块上传：模拟中断恢复，确认断点续传和合并失败回滚。
