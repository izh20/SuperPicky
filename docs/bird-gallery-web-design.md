# 鸟类图库管理网站实现方案

> 方案日期: 2026-04-04  
> 更新日期: 2026-04-04（已根据实际部署环境与代码审查全面修订）

## Context

**部署目标：Mac Mini M4 16GB（macOS），外网通过 DDNS + 路由器端口转发访问，≤10 人使用，暂不启用 SSL。**

**核心约束：**
- 新增功能**不得影响**现有 SuperPicky 桌面 GUI（PySide6）、CLI 工具、Lightroom 插件（Flask :5156）的正常运行
- FastAPI 图库服务作为**独立进程**运行于 `bird-gallery-web/` 子目录，通过 Python `sys.path` 复用现有模块
- ≤10 用户无高并发，SQLite + WAL 足够，无需 PostgreSQL 或 Redis
- 仅考虑 macOS 开发与部署，不需要 Docker 或跨平台方案

**现有服务保留（不动）：**

| 服务 | 端口 | 状态 |
|------|------|------|
| Flask BirdID Server | 5156 | **保留**，供 Lightroom 插件使用 |
| PySide6 桌面 GUI | — | **保留**，本地桌面程序不变 |
| CLI (`superpicky_cli.py`) | — | **保留**，命令行工具不变 |
| FastAPI 图库服务 | 8000 | **新增**，供 Web 前端使用 |

---

## 架构概览

```
                    ┌──────────────────┐
                    │   外网用户浏览器   │
                    └────────┬─────────┘
                             │ HTTP (端口转发 → 80)
                             ▼
                    ┌──────────────────────┐
                    │   nginx 反向代理 :80  │
                    │  静态文件 + API + 大文件上传  │
                    └───┬──────────────┬───┘
                        │              │
               /api/*   │              │  / (静态文件)
                        ▼              ▼
              ┌──────────────┐  ┌────────────────────┐
              │  FastAPI     │  │  Vue 3 静态文件     │
              │  Uvicorn:8000│  │  (nginx 直接提供)   │
              └──────┬───────┘  └────────────────────┘
                     │ Python import
      ┌──────────────┼──────────────────┐
      ▼              ▼                  ▼
┌──────────┐  ┌──────────────┐  ┌──────────────────┐
│ 鸟类识别  │  │  评分引擎     │  │  ExifTool 管理    │
│(复用)     │  │ (复用)        │  │  (复用)           │
└──────────┘  └──────────────┘  └──────────────────┘
      │
      ▼
AI 模型 (MPS 加速，按需加载 + LRU 释放)
SQLite gallery.db + 本地文件系统

──────────────────────────────────────────
独立运行，互不干扰：
┌────────────────────────────────────────┐
│  Flask BirdID Server :5156 (保留不动)  │
│  供 Lightroom 插件调用                  │
└────────────────────────────────────────┘
```

---

## 技术选型

| 组件 | 技术 | 理由 |
|------|------|------|
| 后端框架 | **FastAPI + Uvicorn** | 异步、自动文档，与现有 Python 代码直接 import |
| 前端框架 | **Vue 3 + Vite** | 轻量，配合 `vue-virtual-scroller` 实现大量照片虚拟滚动 |
| 数据库 | **SQLite + WAL** | ≤10 用户无需 PostgreSQL；与现有 `report_db` 模式一致 |
| 文件存储 | **本地文件系统** | Mac Mini 本地磁盘，缩略图由 nginx 直传 |
| 视频处理 | **FFmpeg + OpenCV** | macOS brew 安装，帧提取标准方案；连拍合成也用 FFmpeg |
| 系统依赖 | **FFmpeg** | 必须预装：`brew install ffmpeg` |
| 反向代理 | **nginx** | 静态文件服务、API 代理、HTTP Basic Auth |
| 进程管理 | **launchd** | macOS 原生，开机自启、崩溃自重启 |
| 认证 | **HTTP Basic Auth（nginx）** | ≤10 人场景足够，`.htpasswd` 管理用户 |
| 大文件上传 | **nginx + 分片处理** | 直接用 nginx 上传，后端 Python 合并；支持 10GB 单文件 / 50GB 文件夹 |
| 前端上传 | **Web Upload API** | 使用 `fetch` + `ReadableStream` 实现进度显示 |

**已从原方案移除：** Docker、docker-compose、Dockerfile、PostgreSQL、Celery、Redis、NVIDIA GPU 支持、多平台配置

---

## 核心功能模块

### 1. 照片管理模块

**功能：**
- 批量上传照片（JPG / RAW / HEIF），文件类型白名单校验
- 多级缩略图懒生成（200px 网格 / 800px 详情 / 2000px 全屏）
- EXIF 元数据提取（相机/镜头/ISO/快门/GPS/拍摄日期）
- 照片分类浏览（按日期 / 鸟种 / 评分 / 相机 / 地点）
- 照片整理（去重/相似检测、连拍分组、鸟种索引）
- 现有照片库扫描导入（不移动原始文件）

**复用现有代码（通过 import）：**
- `ai_model.py` — YOLO 检测
- `birdid/bird_identifier.py` — 鸟类分类识别（11000 种）
- `core/keypoint_detector.py` — 关键点检测（眼/喙可见性）
- `core/rating_engine.py` — 评分（-1 到 3 星）
- `core/burst_detector.py` — 连拍分组
- `core/recursive_scanner.py` — 目录递归扫描
- `tools/exiftool_manager.py` — EXIF 读写（持久常驻进程）
- `tools/i18n.py` — 国际化（zh_CN / en_US）
- `tools/memory_monitor.py` — 内存监控（暴露为 `/api/admin/metrics`）

**AI 模型内存管理策略：**

| 模型 | 内存占用 | 策略 |
|------|----------|------|
| YOLO11l-seg | ~150MB | **常驻**（轻量，检测必需） |
| TOPIQ 美学 | ~200MB | **LRU 缓存**，5 分钟无调用则释放 |
| 关键点 ResNet50 | ~400MB | **LRU 缓存**，5 分钟无调用则释放 |
| OSEA BirdID | ~500MB | **LRU 缓存**，5 分钟无调用则释放 |
| Faiss 索引 | ~100MB/百万图 | 按需加载 |

**Mac Mini M4 16GB 内存评估：**
- macOS 系统 + 日常应用（浏览器等）：~6GB
- 仅 Web 端所有模型：~1.5GB（YOLO + OSEA + Keypoint + TOPIQ + Faiss）
- Web + Flask 双份模型（最坏情况）：~3GB
- 最坏场景（日常应用 + 双份模型）：~9GB → 剩余约 7GB，满足需求
- 服务器空闲场景（无日常应用）：~3GB 系统 + ~3GB 双份 = ~6GB → 剩余约 10GB，非常充裕

**模型释放触发条件：**
- 距上次调用 > 5 分钟
- 系统可用内存 < 2GB（触发 OOM 保护）
- 用户可手动触发"释放空闲模型"

**MPS 兼容性说明：**

| 组件 | MPS 支持 | 备注 |
|------|---------|------|
| YOLO11 (Ultralytics) | ✅ 支持 | `device='mps'` 即自动启用 |
| PyTorch 基础操作 | ✅ 支持 | 所有标准张量运算 |
| ResNet50 (关键点) | ✅ 支持 | 标准 ImageNet 架构 |
| TOPIQ 美学模型 | ✅ 支持 | 标准 PyTorch 模型 |
| OSEA BirdID | ✅ 支持 | 标准 PyTorch 模型 |

> ⚠️ **注意：** Mac Mini M4 采用统一内存架构，GPU 共享系统内存。本方案所有模型均使用 MPS（Metal Performance Shaders）加速，不依赖独立 GPU 显存。

**RAW 文件 Web 预览方案：**

| 级别 | 尺寸 | 生成方式 |
|------|------|----------|
| 小缩略图 | 200px | 从 RAW 内嵌 JPEG 提取 → Pillow resize |
| 中预览 | 800px | 同上 |
| 大预览 | 2000px | rawpy 半尺寸解码 + Pillow（回退方案） |

缩略图存储在 `bird-gallery-web/data/thumbnails/{photo_id}/`，懒生成并缓存，由 nginx 直接提供（不经 Python）。

**上传限制：**
| 类型 | 限制 |
|------|------|
| 单文件大小 | **10GB**（支持 RAW / 视频大文件） |
| 文件夹批量上传 | **50GB**（分片上传 + 断点续传） |
| nginx 上传超时 | `client_max_body_size 10G; proxy_read_timeout 1800s;` |

### 2. 视频分析模块（新增）

**功能：**
- 视频上传（MP4 / MOV / AVI / MKV），自动转码为浏览器兼容 H.264 MP4
- 帧采样分析（提供四档采样策略供选择）
- 每帧 YOLO 检测 + 鸟类识别，结果写入 `video_frames` 表
- 时间轴标注（鸟种出现时间段）
- 视频流式播放（nginx HTTP Range 请求）
- **连拍照片导入 + 合成视频**（见 6.3 节）

**视频转码后台处理：**

| 步骤 | 处理 | 说明 |
|------|------|------|
| 1 | 上传原始视频 | 存储到 `data/videos/original/` |
| 2 | 后台转码 | FastAPI BackgroundTasks 调用 FFmpeg 转 H.264 |
| 3 | 前端轮询进度 | GET `/api/tasks/{task_id}` 查询状态 |
| 4 | 转码完成 | 存储到 `data/videos/transcoded/` |
| 5 | 开始帧分析 | 使用转码后的 MP4 |

**转码命令示例：**
```bash
ffmpeg -i input.mov -c:v libx264 -crf 23 -preset fast -c:a aac -b:a 128k output.mp4
```

**后台任务状态（与 DB `videos.status` / `tasks.status` 对齐）：**
```
pending → transcoding (转码中) → processing (分析中，进度 %) → done / error
```

**前端进度显示：**
- 实时显示转码进度百分比
- 可取消任务
- 预估剩余时间

**帧采样策略：**

| 策略 | 方法 | 推荐场景 |
|------|------|----------|
| 关键帧 | `ffmpeg -vf select='eq(pict_type,I)'` | 快速概览 |
| 固定间隔（默认） | 每 10 帧（≈0.33 秒/帧 @30fps） | 常规分析 |
| 场景变化 | OpenCV 帧差，差异>阈值时取帧 | 精准，较慢 |
| 全帧 | 逐帧分析 | 用户手动选，界面显示预计耗时 |

**处理时间估算（Mac Mini M4，MPS 推理）：**
- 单帧（YOLO + BirdID）：约 0.3s
- 10s 视频，间隔采样（30 帧）：约 10-15s
- 10s 视频，全帧（300 帧）：约 90-150s

**视频分析结果展示：**

| 内容 | 说明 |
|------|------|
| **视频缩略图时间轴** | 显示鸟种出现的时间点标记，点击跳帧 |
| **鸟种清单** | 视频中出现的所有鸟种列表（按出现频次排序） |
| **每帧详情** | 每帧的识别结果、置信度、边界框可视化 |
| **最佳帧推荐** | 自动选出每种鸟类的最佳一帧（置信度×清晰度最高） |
| **鸟种出现时段** | 每种鸟在视频中出现的时间段（如"白鹭：00:05-00:12"） |
| **统计摘要** | 总帧数、检测到鸟类的帧数、识别置信度分布 |

**API 接口：**
```
POST /api/videos/upload               上传视频
GET  /api/videos/{id}                 视频详情
GET  /api/videos/{id}/stream          流式播放（nginx Range 请求）
POST /api/videos/{id}/analyze         发起分析（返回 task_id）
GET  /api/videos/{id}/frames          获取帧分析结果列表
GET  /api/videos/{id}/timeline        获取鸟种出现时间轴
GET  /api/videos/{id}/highlights      获取精彩片段列表
POST /api/videos/{id}/export-clip     导出指定时间段的视频片段
```

**视频分析结果展示（让用户觉得好用的关键）：**

分析完成后，前端应展示以下内容：

**① 视频概览卡片**
- 视频封面缩略图 + 时长 + 分辨率
- 检测到的鸟种数量、出现总次数
- 最佳帧截图（置信度最高的那一帧）

**② 鸟种出现时间轴（核心体验）**
```
时间轴 ─────────────────────────────────────────►
        ██ 白鹭 (00:02-00:08)
              ████ 白头鹎 (00:05-00:15)
                           ██ 翠鸟 (00:12-00:14)
```
- 横轴为视频时间，每种鸟用不同颜色的条带标注出现时段
- 点击时间条可跳转到视频对应位置播放
- 悬浮显示置信度和帧截图预览

**③ 鸟种统计面板**
| 鸟种 | 出现时长 | 帧数 | 最高置信度 | 最佳帧截图 |
|------|---------|------|-----------|-----------|
| 白鹭 | 6.2s | 18帧 | 96.3% | [查看] |
| 白头鹎 | 10.1s | 30帧 | 89.7% | [查看] |

**④ 精彩帧画廊**
- 自动筛选每种鸟种置信度最高的 Top 3 帧
- 展示帧截图 + 检测框标注 + 鸟种名称 + 时间戳
- 支持一键保存为照片（添加到图库）

**⑤ 视频播放器（增强版）**
- 原始视频播放 + 叠加实时检测框标注
- 进度条上标注鸟种出现区间（彩色标记）
- 支持"跳转到下一只鸟"快捷按钮
- 支持导出指定时间段的视频片段

### 3. 鸟类识别模块

**功能：**
- 单张 / 批量照片识别
- 视频帧批量识别
- 识别结果存储（多候选，排名 + 置信度）
- 鸟种信息展示（中文名 / 英文名 / 学名 / 描述）

**评分系统说明（-1 到 3 星，非 EXIF 的 0-5 星）：**

| SuperPicky 评分 | 含义 | Web 展示 |
|-----------------|------|----------|
| -1 | 无鸟检测到 | 标记"无鸟类" |
| 0 | 不合格（放弃） | ☆☆☆ |
| 1 | 普通合格 | ★☆☆ |
| 2 | 良好 | ★★☆ |
| 3 | 优选 | ★★★ |

### 4. 图库浏览模块

**功能：**
- 网格 / 列表视图（虚拟滚动，支持数万张图片）
- 多条件组合筛选（AND 逻辑）
- 搜索（鸟种中文名 / 英文名 / 学名）
- 照片详情（EXIF 全信息 + 识别结果 + 评分）

**EXIF 筛选字段：**

| 筛选字段 | EXIF 标签 | 示例 |
|----------|-----------|------|
| 相机型号 | `Make` + `Model` | Canon EOS R5 |
| 镜头型号 | `LensModel` | RF 100-500mm |
| 光圈 | `FNumber` | f/5.6 |
| 快门速度 | `ExposureTime` | 1/2000s |
| ISO | `ISO` | 1600 |
| 焦距 | `FocalLength` | 500mm |
| 拍摄日期 | `DateTimeOriginal` | 按日期范围 |
| GPS 地点 | `GPSLatitude/Longitude` | 按区域筛选 |
| 评分 | SuperPicky rating | -1 到 3 |

### 5. 用户管理模块（简化版）

≤10 人场景，不需要完整注册/登录系统：

- **nginx 层 HTTP Basic Auth**（`.htpasswd` 文件管理用户，`htpasswd` 命令添加/删除）
- FastAPI 从请求头获取已认证用户名，用于标记操作者
- 后续可升级为 Token 或 OAuth2，不影响 API 接口设计

### 6. 照片整理模块（去重 + 鸟种索引）

#### 6.1 重复 / 相似照片检测

**技术方案：**

| 方法 | 技术 | 说明 |
|------|------|------|
| 精确重复 | `hashlib` SHA256 | 同一文件多次上传 |
| 视觉相似 | `imagehash` pHash/dHash | 感知哈希，连拍同场景 |
| 连拍分组 | EXIF `DateTimeOriginal` | 复用 `core/burst_detector.py` |

**相似度阈值：**

| 等级 | Hamming 距离 | 说明 |
|------|-------------|------|
| 完全相同 | 0 | 同一文件 |
| 几乎相同 | ≤ 5 | 同一照片不同处理版本 |
| 高度相似 | ≤ 10 | 连拍或近似角度 |
| 相似 | ≤ 20 | 可能同一场景 |

**API 接口：**
```
POST /api/photos/find-duplicates
GET  /api/photos/groups/{group_id}
POST /api/photos/groups/{group_id}/keep/{photo_id}
```

#### 6.2 鸟种照片索引

**索引结构（符号链接，不复制文件）：**
```
bird-gallery-web/data/gallery/by_bird/
├── 白头鹎_Light-vented_Bulbul_Pycnonotus_sinensis/
│   ├── IMG_0001.jpg -> /原始路径/IMG_0001.jpg  (符号链接)
│   └── IMG_0002.jpg -> /原始路径/IMG_0002.jpg
├── 白鹭_Eastern_Great_Egret_Ardea_alba/
│   └── ...
└── 未识别/
    └── ...
```

文件策略：**原始文件不移动**，`by_bird/` 目录全部使用 macOS 符号链接；若源文件丢失，前端标记"文件缺失"。

**API 接口：**
```
GET  /api/birds                     列出所有已识别鸟种
GET  /api/birds/{species}/photos    某鸟种的所有照片
POST /api/birds/organize            重新生成鸟种符号链接目录
GET  /api/birds/stats               鸟种统计
```

#### 6.3 连拍照片识别与合成视频

**功能：**
- 自动检测连拍照片组（复用 `core/burst_detector.py`，基于 EXIF `DateTimeOriginal` 时间戳间隔）
- 对连拍组内所有照片进行批量鸟类识别
- 连拍组内照片自动评分排序（锐度 + 美学），标记"最佳一张"
- 将连拍照片序列合成为延时/慢动作视频（FFmpeg `image2` 方式）
- 连拍组合筛选和浏览

**连拍检测参数（可用户配置）：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `burst_time_threshold` | 250ms | 相邻照片时间间隔阈值（同一相机） |
| `burst_min_count` | 4 | 最少连拍张数才算一组 |
| `use_phash` | false | 可选启用 pHash 验证连拍相似性 |

**连拍合成视频配置：**

| 参数 | 默认值 | 可调 |
|------|--------|------|
| 每帧显示时长 | 1/20s（50ms） | 1/30s ~ 1s（可滑动选择） |
| 分辨率 | 1920x1080 | 4K / 1080p / 720p |
| 等效帧率 | 20fps（由每帧时长决定） | 1fps ~ 30fps |
| 视频格式 | H.264 MP4 | H.265 / ProRes（Mac） |
| 过渡效果 | 无 | 淡入淡出 |

**连拍合成视频流程：**
```
连拍组照片 → 按时间戳排序 → 生成缩略图序列（统一尺寸）
    → FFmpeg 合成为 H.264 MP4 → 可选叠加鸟种名称水印
    → 保存到 data/videos/burst_{group_id}.mp4
```

**合成命令示例：**
```bash
ffmpeg -framerate 20 -i frame_%04d.jpg -c:v libx264 -pix_fmt yuv420p burst_output.mp4
# 20fps = 每帧 1/20s；用户选1s/帧时改为 -framerate 1
```

**前端展示：**
- 连拍组以"卡片堆叠"样式展示，显示张数和最佳帧预览
- 展开后显示所有帧的缩略图时间线，标注每帧评分
- "合成视频"按钮 → 滑动选择单帧显示时长（1/30s ~ 1s，默认 1/20s）→ 后台生成 → 完成后可在线播放/下载
- 连拍组内鸟种识别结果汇总（取所有帧中置信度最高的结果）

**API 接口：**
```
POST /api/photos/detect-bursts           检测连拍组（返回 task_id）
GET  /api/bursts                         列出所有连拍组
GET  /api/bursts/{group_id}              连拍组详情（含所有帧+评分+识别结果）
GET  /api/bursts/{group_id}/best         获取组内最佳照片
POST /api/bursts/{group_id}/recognize    批量识别连拍照片
POST /api/bursts/{group_id}/synthesize   合成视频（选单帧时长，返回 task_id）
GET  /api/bursts/{group_id}/video        获取合成后的视频
```

---

## 数据库 Schema（`gallery.db`，独立于现有 `report.db`）

```sql
-- 照片索引
CREATE TABLE photos (
    id           TEXT PRIMARY KEY,   -- UUID
    original_path TEXT NOT NULL,     -- 原始文件绝对路径
    filename     TEXT NOT NULL,
    file_hash    TEXT,               -- SHA256，用于精确去重
    width        INTEGER,
    height       INTEGER,
    file_size    INTEGER,
    imported_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- EXIF 元数据
CREATE TABLE photo_metadata (
    photo_id     TEXT PRIMARY KEY REFERENCES photos(id),
    camera_make  TEXT, camera_model TEXT, lens_model TEXT,
    iso          INTEGER, shutter_speed TEXT, aperture REAL,
    focal_length REAL, focal_length_35mm REAL,
    gps_lat      REAL, gps_lon REAL, gps_altitude REAL,
    date_taken   DATETIME, timezone TEXT
);

-- 鸟类识别结果（一张照片可有多只鸟，多个候选）
CREATE TABLE photo_birds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id        TEXT REFERENCES photos(id),
    species_cn      TEXT, species_en TEXT, scientific_name TEXT,
    confidence      REAL, rank INTEGER,
    detection_box   TEXT  -- JSON: [x1,y1,x2,y2]
);

-- 评分数据
CREATE TABLE photo_scores (
    photo_id     TEXT PRIMARY KEY REFERENCES photos(id),
    rating       INTEGER,   -- -1 到 3
    head_sharp   REAL,      -- 头部锐度
    nima_score   REAL,      -- 美学评分 1-10
    is_flying    INTEGER,   -- 0/1
    focus_status TEXT,      -- BEST/GOOD/BAD/WORST
    exposure_status TEXT    -- 正常/过曝/欠曝
);

-- 视频
CREATE TABLE videos (
    id           TEXT PRIMARY KEY,
    original_path TEXT NOT NULL,
    filename     TEXT,
    duration     REAL,  -- 秒
    fps          REAL,
    frame_count  INTEGER,
    status       TEXT DEFAULT 'pending',  -- pending/transcoding/processing/done/error
    imported_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 视频帧分析结果
CREATE TABLE video_frames (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id     TEXT REFERENCES videos(id),
    frame_number INTEGER,
    timestamp    REAL,   -- 秒
    bird_detected INTEGER,
    species_cn   TEXT, species_en TEXT,
    confidence   REAL,
    detection_box TEXT,  -- JSON: [x1,y1,x2,y2]
    frame_path   TEXT    -- 帧截图文件路径
);

-- 视频鸟种出现时段汇总（从 video_frames 聚合）
CREATE TABLE video_bird_segments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id     TEXT REFERENCES videos(id),
    species_cn   TEXT, species_en TEXT,
    start_time   REAL,   -- 秒
    end_time     REAL,
    max_confidence REAL,
    best_frame_number INTEGER,
    best_frame_path   TEXT
);

-- 连拍组
CREATE TABLE burst_groups (
    id              TEXT PRIMARY KEY,   -- UUID
    photo_count     INTEGER,
    best_photo_id   TEXT REFERENCES photos(id),
    avg_rating      REAL,
    species_cn      TEXT, species_en TEXT,  -- 组内最高置信度鸟种
    max_confidence  REAL,
    video_path      TEXT,               -- 合成视频路径（可为空）
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 连拍组-照片关联
CREATE TABLE burst_group_photos (
    group_id     TEXT REFERENCES burst_groups(id),
    photo_id     TEXT REFERENCES photos(id),
    position     INTEGER,  -- 组内排序位置
    PRIMARY KEY (group_id, photo_id)
);

CREATE INDEX idx_burst_group_photos_group ON burst_group_photos(group_id);

-- 用户标签
CREATE TABLE tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    created_by TEXT
);
CREATE TABLE photo_tags (
    photo_id TEXT REFERENCES photos(id),
    tag_id   INTEGER REFERENCES tags(id),
    PRIMARY KEY (photo_id, tag_id)
);

-- 去重分组
CREATE TABLE duplicate_groups (
    group_id   TEXT NOT NULL,
    photo_id   TEXT REFERENCES photos(id),
    hash_type  TEXT,   -- 'exact'/'phash'/'dhash'
    similarity REAL,
    PRIMARY KEY (group_id, photo_id)
);

-- 分块上传会话追踪
CREATE TABLE upload_sessions (
    id              TEXT PRIMARY KEY,   -- upload_id
    filename        TEXT NOT NULL,
    file_size       INTEGER,            -- bytes
    chunk_count     INTEGER,            -- 预期分块总数
    chunk_size      INTEGER DEFAULT 10485760,  -- 10MB/块
    status          TEXT DEFAULT 'uploading',  -- uploading/completed/failed
    uploaded_chunks TEXT,                -- JSON: [0, 1, 2, ...] 已接收的块编号
    file_hash       TEXT,                -- SHA256 最终校验
    file_type       TEXT,                -- 'photo' / 'video'
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 异步任务
CREATE TABLE tasks (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,  -- 'recognize'/'analyze'/'scan'/'organize'
    status      TEXT DEFAULT 'pending',  -- pending/running/done/error
    progress    INTEGER DEFAULT 0,       -- 0-100
    result_json TEXT,
    error_msg   TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 数据库索引（提升查询性能）
CREATE INDEX idx_photos_hash ON photos(file_hash);
CREATE INDEX idx_metadata_camera ON photo_metadata(camera_model);
CREATE INDEX idx_metadata_lens ON photo_metadata(lens_model);
CREATE INDEX idx_metadata_date ON photo_metadata(date_taken);
CREATE INDEX idx_scores_rating ON photo_scores(rating);
CREATE INDEX idx_photo_birds_photo ON photo_birds(photo_id);
CREATE INDEX idx_photo_birds_species_cn ON photo_birds(species_cn);
CREATE INDEX idx_photo_birds_species_en ON photo_birds(species_en);
CREATE INDEX idx_video_frames_video ON video_frames(video_id);
CREATE INDEX idx_video_frames_species ON video_frames(species_cn);
CREATE INDEX idx_video_bird_segments_video ON video_bird_segments(video_id);
CREATE INDEX idx_burst_groups_created ON burst_groups(created_at);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_duplicate_groups_hash ON duplicate_groups(hash_type);
CREATE INDEX idx_upload_sessions_status ON upload_sessions(status);
CREATE INDEX idx_upload_sessions_created ON upload_sessions(created_at);
```

---

## 完整 API 设计

### 照片

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/photos/upload` | 上传照片（支持批量，multipart/form-data，单文件 ≤10GB） |
| POST | `/api/photos/upload-folder` | 文件夹上传（总量 ≤50GB，分块上传） |
| GET | `/api/photos` | 列表查询（分页 + 多条件筛选） |
| GET | `/api/photos/{id}` | 照片详情（含 EXIF、识别结果、评分） |
| GET | `/api/photos/{id}/thumbnail?size=sm\|md\|lg` | 缩略图（nginx 直传） |
| GET | `/api/photos/{id}/original` | 原图下载（需 Basic Auth） |
| POST | `/api/photos/{id}/recognize` | 单张识别（串行化推理） |
| POST | `/api/photos/batch-recognize` | 批量识别（返回 task_id） |
| POST | `/api/photos/find-duplicates` | 查找重复/相似照片（返回去重组列表） |
| GET | `/api/photos/groups/{group_id}` | 查看去重组详情（组内所有照片 + 相似度） |
| POST | `/api/photos/groups/{group_id}/keep/{photo_id}` | 保留指定照片，标记组内其他为冗余 |
| DELETE | `/api/photos/{id}` | 删除索引（不删源文件），级联删除关联的 metadata/scores/birds 数据，缩略图保留（可清理） |

### 视频

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/videos/upload` | 上传视频（单文件 ≤10GB，分块上传） |
| GET | `/api/videos/{id}` | 视频详情 |
| GET | `/api/videos/{id}/stream` | 视频流（nginx Range 请求） |
| POST | `/api/videos/{id}/analyze` | 分析视频（返回 task_id） |
| GET | `/api/videos/{id}/frames` | 帧分析结果列表 |
| GET | `/api/videos/{id}/timeline` | 鸟种出现时间轴数据 |
| GET | `/api/videos/{id}/highlights` | 精彩帧截图列表 |
| POST | `/api/videos/{id}/export-clip` | 导出指定时间段片段 |

### 连拍

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/photos/detect-bursts` | 检测连拍组（异步，返回 task_id） |
| GET | `/api/bursts` | 列出所有连拍组 |
| GET | `/api/bursts/{group_id}` | 组详情（所有帧 + 评分 + 识别） |
| GET | `/api/bursts/{group_id}/best` | 组内最佳照片 |
| POST | `/api/bursts/{group_id}/recognize` | 批量识别连拍照片 |
| POST | `/api/bursts/{group_id}/synthesize` | 合成视频（选单帧时长，返回 task_id） |
| GET | `/api/bursts/{group_id}/video` | 获取合成视频 |

### 鸟种

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/birds` | 所有已识别鸟种 |
| GET | `/api/birds/{species}/photos` | 某鸟种照片 |
| POST | `/api/birds/organize` | 重建符号链接目录（异步） |
| GET | `/api/birds/stats` | 鸟种统计 |

### 图库管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/library/scan` | 扫描本地目录导入（返回 task_id） |
| GET | `/api/tasks/{task_id}` | 查询异步任务状态与进度 |
| GET | `/api/stats/dashboard` | 仪表盘统计（照片数/鸟种数/最近活动） |
| GET | `/api/admin/health` | 服务健康检查 |
| GET | `/api/admin/metrics` | 系统指标（内存/CPU/模型状态） |

**`/api/admin/metrics` 返回内容：**
```json
{
  "memory": {
    "system_total_gb": 16,
    "system_used_gb": 10.2,
    "app_used_gb": 2.1
  },
  "models": {
    "yolo": { "loaded": true, "memory_mb": 150 },
    "topiq": { "loaded": false, "last_used": "2026-04-04T10:30:00" },
    "keypoint": { "loaded": true, "memory_mb": 400 },
    "osea": { "loaded": false, "last_used": "2026-04-04T10:25:00" }
  },
  "tasks": {
    "running": 2,
    "queued": 5
  }
}
```

### EXIF 写入（复用现有能力）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/photos/{id}/exif/write-title` | 写鸟种名到 EXIF Title |
| POST | `/api/photos/{id}/exif/write-caption` | 写描述到 EXIF Caption |

### 大文件分块上传

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/upload/init` | 初始化上传会话，返回 upload_id |
| POST | `/api/upload/{upload_id}/chunk?index=N` | 上传单个分块（10MB/块） |
| GET | `/api/upload/{upload_id}/status` | 查询已上传块列表（断点续传） |
| POST | `/api/upload/{upload_id}/complete` | 合并分块 + SHA256 校验 |

> **注意**：EXIF 中文写入必须使用 UTF-8 temp file 方式（`-Tag<=tmp.txt`），复用 `tools/exiftool_manager.py` 现有实现，不得使用 inline CLI 参数。

### 大文件上传方案

单文件最大 10GB、文件夹最大 50GB，需采用**分块上传（Chunked Upload）**：

**流程：**
```
1. 前端将大文件切片（每块 10MB）
2. POST /api/upload/init → 获取 upload_id
3. 循环 POST /api/upload/{upload_id}/chunk?index=N → 上传每块
4. POST /api/upload/{upload_id}/complete → 服务端合并 + 校验 SHA256
```

**断点续传：**
- 每块上传成功后服务端记录已接收的块编号
- 前端中断后可查询 `GET /api/upload/{upload_id}/status` 获取已上传块列表
- 仅重传缺失的块

**nginx 配置要点：**
```nginx
proxy_request_buffering off;   # 流式转发，不缓存到磁盘
client_max_body_size 10G;      # 单请求上限
proxy_read_timeout 1800s;      # 大文件上传超时放宽（10GB@10MB/s≈17min）
proxy_send_timeout 1800s;
```

---

## AI 模型文件清单（必须准备齐全）

| 模型 | 文件名 | 来源仓库 | 用途 |
|------|--------|----------|------|
| YOLO11L-Seg | `yolo11l-seg.pt` | Ultralytics | 鸟类检测 + 实例分割 |
| OSEA ResNet34 | `model20240824.pth` | `jamesphotography/SuperPicky-models` | 鸟类分类（11000 种） |
| EfficientNet-B3 | `superFlier_efficientnet.pth` | `jamesphotography/SuperPicky-models` | 飞行状态检测 |
| ResNet50 Keypoint | `cub200_keypoint_resnet50_slim.pth` | `jamesphotography/SuperPicky-models` | 关键点检测（眼/喙） |
| CFANet ResNet50 | `cfanet_iaa_ava_res50-3cd62bb3.pth` | `chaofengc/IQA-PyTorch-Weights` | 美学评分（TOPIQ） |

**数据库文件（同样必须）：**
- `birdid/data/bird_reference.sqlite` — 鸟种参考数据库（中/英/学/eBird 代码）
- `ioc/birdname.db` — eBird 鸟种名称数据库
- `birdid/data/avonet.db` — AVOnet 形态学数据库

**Mac Mini M4 16GB 内存分配估算（仅推理，无 optimizer）：**
- 所有模型（Web 端）：约 1.5GB（YOLO 150MB + OSEA 500MB + Keypoint 400MB + TOPIQ 200MB + Faiss ~100MB）
- Web + Flask 双份：约 3GB
- 系统 + nginx + Python 环境：约 3GB
- 剩余可用：约 11GB+（充裕，日常使用完全不受影响）

---

## GPU 推理串行化

≤10 用户场景不会有密集并发推理，但多请求同时触发 MPS 推理仍可能导致显存溢出或排队混乱，使用 `asyncio.Lock` 串行化：

```python
# bird-gallery-web/backend/main.py
import asyncio
_inference_lock = asyncio.Lock()

# 在各识别 endpoint 中使用
async with _inference_lock:
    result = await run_in_threadpool(identify_bird, image_path, ...)
```

- 模型实例通过 `_lazy_registry`（现有代码）单例复用
- FastAPI 启动时可选预热（`startup` 事件中调用 `ensure_models_loaded()`）
- Flask :5156 与 FastAPI :8000 各自独立进程，各自加载模型实例，**不共享**（相当于模型内存占用翻倍，双份约 3GB + 系统约 3GB = 总计约 6GB，M4 16GB 完全可承受）

### 模型生命周期管理（按需加载 + 超时释放）

Mac Mini 还要干其他事情（日常使用、其他服务），模型不应无限期常驻。采用 **按需加载 + 空闲超时释放** 策略：

**内存占用评估：**

| 状态 | 统一内存占用 | 剩余可用 |
|------|-------------|----------|
| 无模型（空闲） | 系统+nginx+Python ≈ 3GB | ≈ 13GB |
| 仅 Web 端所有模型 | ≈ 1.5GB | ≈ 11GB |
| Web + Flask 双份 | ≈ 3GB | ≈ 11GB |

**常驻的潜在问题：**
1. macOS 统一内存被 PyTorch MPS 张量占满后，系统会频繁 swap → 整机变卡
2. 其他应用（浏览器、Lightroom、Final Cut 等）可用内存不足
3. Flask :5156 也加载模型时双倍占用

**推荐策略：空闲超时自动卸载（TTL = 5 分钟）**

```python
import time, threading, torch, gc

class ModelManager:
    """模型按需加载 + 空闲超时释放"""
    TTL_SECONDS = 5 * 60  # 5 分钟无请求则释放

    def __init__(self):
        self._models = {}          # name → model instance
        self._last_used = {}       # name → timestamp
        self._lock = threading.Lock()
        self._start_cleanup_timer()

    def get(self, name: str, loader_fn):
        """获取模型，未加载则按需加载"""
        with self._lock:
            if name not in self._models:
                self._models[name] = loader_fn()
            self._last_used[name] = time.time()
            return self._models[name]

    def _cleanup(self):
        """释放超过 TTL 未使用的模型"""
        now = time.time()
        with self._lock:
            expired = [k for k, t in self._last_used.items()
                       if now - t > self.TTL_SECONDS]
            for name in expired:
                del self._models[name]
                del self._last_used[name]
            if expired:
                if torch.backends.mps.is_available():
                    torch.mps.empty_cache()
                gc.collect()

    def _start_cleanup_timer(self):
        def loop():
            while True:
                time.sleep(60)
                self._cleanup()
        t = threading.Thread(target=loop, daemon=True)
        t.start()
```

**效果：**
- 用户访问时：模型按需加载（首次约 3-5 秒），后续请求复用
- 5 分钟无人访问：自动释放全部模型，`torch.mps.empty_cache()` 归还显存
- Mac Mini 空闲时仅占 ≈3GB，不影响其他日常使用
- TTL 可通过环境变量 `MODEL_TTL_MINUTES` 配置（默认 5）

---

## 异步任务处理

长耗时操作（视频分析、批量识别、目录扫描）使用 FastAPI `BackgroundTasks` + `tasks` 表：

```
客户端：POST /api/videos/{id}/analyze
         ← 立即返回 { task_id: "uuid" }

后台：BackgroundTask 开始处理，每帧完成后更新 tasks.progress

客户端轮询：GET /api/tasks/{task_id}（间隔 2 秒）
         ← { status: "running", progress: 45, result: null }

完成后：← { status: "done", progress: 100, result: {...} }
```

不使用 Celery/Redis，减少运维复杂度，`BackgroundTasks` 对于 ≤10 用户场景完全足够。

---

## 安全防护

**文件上传：**
- 文件类型白名单（MIME + 扩展名双重校验）：
  - 图片：`.jpg .jpeg .png .heif .heic .cr2 .nef .arw .dng .raf .orf .rw2`
  - 视频：`.mp4 .mov .avi .mkv`
- 上传大小限制：nginx `client_max_body_size 10G`（单文件）+ FastAPI 校验；文件夹批量上传总量限制 50GB
- 文件名清洗：去除路径分隔符和特殊字符，防止路径穿越

**API 安全：**
- `scan_path` / `image_path` 等路径参数做**目录白名单校验**（仅允许预设的照片根目录下的路径）
- FastAPI 启用 CORS，仅允许 DDNS 域名
- nginx 隐藏版本号（`server_tokens off`）

**认证（暂不启用 SSL 时）：**
- nginx HTTP Basic Auth 保护全站（包括 `/api/`）
- 后续加 SSL 后，Basic Auth 的明文密码问题自动解决

---

## nginx 配置

```nginx
# /opt/homebrew/etc/nginx/servers/birdgallery.conf

server {
    listen 80;
    server_name your-ddns-host.example.com;  # 替换为你的 DDNS 域名

    server_tokens off;
    client_max_body_size 10G;   # 单文件最大 10GB（视频等大文件）
    proxy_request_buffering off;  # 大文件流式转发，不缓存到磁盘

    # HTTP Basic Auth（保护全站）
    auth_basic "Bird Gallery";
    auth_basic_user_file /opt/homebrew/etc/nginx/.htpasswd;

    # Vue 3 前端静态文件
    location / {
        root /Users/zhouheng/claude/SuperPicky/bird-gallery-web/frontend/dist;
        try_files $uri $uri/ /index.html;
        expires 1h;
    }

    # 缩略图直传（高性能，不经 Python，并且支持未找到时回退给 FastAPI 去懒生成）
    location /data/thumbnails/ {
        alias /Users/zhouheng/claude/SuperPicky/bird-gallery-web/data/thumbnails/;
        expires 7d;
        add_header Cache-Control "public, immutable";
        try_files $uri @fastapi; # 如果没找到，转发给 FastAPI 去懒生成
    }

    # Nginx 请求直接回退到 FastAPI
    location @fastapi {
        proxy_pass http://127.0.0.1:8000;
    }

    # 视频流（支持 Range 请求）
    location /data/videos/ {
        alias /Users/zhouheng/claude/SuperPicky/bird-gallery-web/data/videos/;
        mp4;
        add_header Accept-Ranges bytes;
    }

    # FastAPI 代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 1800s;   # 兼容大文件上传和长耗时识别请求
        proxy_send_timeout 1800s;
    }
}
```

**创建用户：**
```bash
htpasswd -c /opt/homebrew/etc/nginx/.htpasswd username1
htpasswd /opt/homebrew/etc/nginx/.htpasswd username2
```

> **后续加 SSL**：只需在此配置中加入 Let's Encrypt 证书路径并监听 443，其他不变。

---

## 目录结构

```
SuperPicky/                           # 现有仓库根目录（不动）
├── ai_model.py                      # 现有代码
├── birdid/                          # 现有代码
├── core/                            # 现有代码
├── tools/                           # 现有代码
├── birdid_server.py                 # 现有 Flask :5156（不动）
├── main.py                          # 现有 GUI 入口（不动）
│
└── bird-gallery-web/                # ★ 新增子目录
    ├── backend/
    │   ├── main.py                  # FastAPI 入口 + sys.path 设置
    │   ├── api/
    │   │   ├── photos.py
    │   │   ├── videos.py
    │   │   ├── birds.py
    │   │   ├── duplicates.py
    │   │   ├── library.py           # 目录扫描导入
    │   │   ├── bursts.py            # 连拍相关 API
    │   │   ├── upload.py            # 分块上传 API
    │   │   └── tasks.py             # 异步任务查询
    │   ├── services/
    │   │   ├── video_processor.py   # FFmpeg 帧提取 + 转码
    │   │   ├── thumbnail_generator.py
    │   │   ├── duplicate_detector.py
    │   │   ├── bird_organizer.py    # 鸟种符号链接整理
    │   │   ├── burst_synthesizer.py  # 连拍合成视频
    │   │   └── upload_manager.py     # 分块上传管理
    │   ├── models/
    │   │   ├── database.py          # SQLite 连接 + Schema 初始化
    │   │   └── schemas.py           # Pydantic 请求/响应模型
    │   └── requirements.txt         # fastapi uvicorn python-multipart imagehash
    │
    ├── frontend/
    │   ├── src/
    │   │   ├── views/               # Gallery / Upload / VideoAnalysis / Dashboard
    │   │   ├── components/          # PhotoGrid / VideoPlayer / BirdCard / FilterPanel
    │   │   └── api/                 # Axios 封装
    │   ├── package.json
    │   └── vite.config.js
    │
    ├── data/                        # 运行时数据（.gitignore 排除）
    │   ├── database/
    │   │   └── gallery.db
    │   ├── thumbnails/
    │   ├── videos/
    │   │   ├── original/            # 上传的原始视频
    │   │   ├── transcoded/          # 转码后的 H.264 MP4
    │   │   └── burst/               # 连拍合成视频
    │   ├── frames/                  # 视频帧缓存
    │   └── gallery/
    │       └── by_bird/             # 符号链接鸟种索引
    │
    └── deploy/
        ├── nginx.conf               # nginx 站点配置（参见上节）
        ├── com.birdgallery.api.plist # launchd 服务定义
        └── setup.sh                 # 一键部署脚本
```

**在 SuperPicky 根目录 `.gitignore` 中添加：**
```
bird-gallery-web/data/
bird-gallery-web/frontend/dist/
bird-gallery-web/frontend/node_modules/
bird-gallery-web/backend/.venv/
```

**FastAPI 后端中复用现有模块的方式：**
```python
# bird-gallery-web/backend/main.py
import sys, os
# 将 SuperPicky 根目录加入 Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from birdid.bird_identifier import identify_bird
from core.rating_engine import RatingEngine
from core.burst_detector import BurstDetector
from tools.exiftool_manager import ExifToolManager
from tools.i18n import get_i18n
```

---

## 部署方案（macOS 原生，替代 Docker）

**环境要求：**
- Mac Mini M4 16GB，macOS 14+
- Homebrew 已安装
- Python 3.11+（SuperPicky 现有 `.venv` 可复用，或新建）

### 部署步骤

```bash
# 1. 安装系统依赖
brew install nginx ffmpeg

# 2. 创建后端虚拟环境
cd /Users/zhouheng/claude/SuperPicky/bird-gallery-web/backend
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn python-multipart imagehash pillow

# 3. 构建前端
cd ../frontend
npm install
npm run build
# 产物输出到 dist/ 目录，nginx 直接服务

# 4. 创建数据目录
mkdir -p ../data/database ../data/thumbnails ../data/videos \
         ../data/frames ../data/gallery/by_bird

# 5. 配置 nginx
sudo cp ../deploy/nginx.conf /opt/homebrew/etc/nginx/servers/birdgallery.conf
sudo nginx -t && sudo brew services restart nginx

# 6. 创建登录用户（首次）
htpasswd -c /opt/homebrew/etc/nginx/.htpasswd your_username

# 7. 注册 launchd 服务（开机自启）
cp ../deploy/com.birdgallery.api.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.birdgallery.api.plist
launchctl start com.birdgallery.api
```

### launchd 服务定义

```xml
<!-- bird-gallery-web/deploy/com.birdgallery.api.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.birdgallery.api</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/zhouheng/claude/SuperPicky/bird-gallery-web/backend/.venv/bin/uvicorn</string>
        <string>main:app</string>
        <string>--host</string><string>127.0.0.1</string>
        <string>--port</string><string>8000</string>
        <string>--workers</string><string>1</string>  <!-- asyncio.Lock 串行化推理，单 worker 足够 -->
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/zhouheng/claude/SuperPicky/bird-gallery-web/backend</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key>
    <string>/tmp/birdgallery-api.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/birdgallery-api-error.log</string>
</dict>
</plist>
```

### 路由器端口转发配置

```
外网端口（如 8080）→ Mac Mini 内网 IP → 端口 80（nginx）
```

访问地址：`http://your-ddns-domain.com:8080`

> **后续加 SSL（Let's Encrypt）：**
> ```bash
> brew install certbot
> sudo certbot --nginx -d your-ddns-domain.com
> # 自动续期：certbot renew（可加入 cron/launchd）
> ```

---

## 验证清单

| # | 验证项 | 方法 |
|---|--------|------|
| 1 | **现有功能不受影响** | 启动图库服务后，确认 Flask :5156 正常响应、GUI 正常启动、CLI `process` 正常运行 |
| 2 | 照片上传 + 识别 | 上传 JPG + RAW，调用识别 API，验证返回鸟种、置信度、评分 |
| 3 | RAW 缩略图 | 上传 `.arw` 或 `.cr2`，确认各尺寸缩略图正常生成并可浏览器访问 |
| 4 | 视频分析 | 上传 10 秒视频，选间隔采样（默认 10 帧），确认任务完成、帧结果正确 |
| 5 | 异步任务 | 发起批量识别，轮询 `/api/tasks/{id}` 确认 progress 递增、最终 done |
| 6 | 重复照片检测 | 上传同一照片两次，`/api/photos/find-duplicates` 检出 |
| 7 | 现有照片库导入 | 提交本地目录路径，扫描完成后 gallery 内可浏览 |
| 8 | 外网访问 | 通过 DDNS 域名 + 端口从外部设备访问，确认 nginx 代理、Basic Auth 正常 |
| 9 | 安全 | 尝试 `scan_path=../../../etc/passwd`，确认被白名单校验拦截 |
| 10 | EXIF 中文写入 | 写入中文鸟种名并读回，验证无乱码（UTF-8 temp file 方式） |
| 11 | 模型自动释放 | 识别完成后等待 5+ 分钟，确认模型已释放（`/api/admin/metrics` 检查内存下降） |
| 12 | 连拍检测 | 上传一组连拍照片（≥4张），确认自动分组、组内评分排序、最佳帧标记 |
| 13 | 连拍合成视频 | 选一组连拍 → 合成 10fps 视频 → 在线播放 → 确认帧顺序正确 |
| 14 | 大文件上传 | 上传 2GB+ 视频文件，验证分块上传、断点续传、合并校验 |
| 15 | 视频分析展示 | 分析完视频后，确认时间轴、鸟种统计、精彩帧截图全部正确展示 |

---

## 分阶段实施计划

### Phase 1：后端基础 + 照片管理（1-2 周）
- FastAPI 骨架、SQLite Schema 初始化
- 照片上传（白名单校验）、缩略图生成（多级）
- EXIF 元数据提取（复用 `exiftool_manager.py`）
- 单张鸟类识别 API（串行化推理）
- nginx 配置 + HTTP Basic Auth
- **验收：** 上传照片 → 生成缩略图 → 识别 → 返回结果

### Phase 2：前端 + 图库浏览（1-2 周）
- Vue 3 项目搭建（Vite + vue-router + pinia）
- 照片网格组件（虚拟滚动，`vue-virtual-scroller`）
- 筛选面板（鸟种/日期/相机/评分多条件）
- 照片详情页（EXIF 全信息 + 识别结果）
- **验收：** 浏览器可浏览图库、筛选、查看详情

### Phase 3：视频分析（1-2 周）
- FFmpeg 帧提取服务（四档采样策略）
- 视频上传 + 转码 + nginx Range 播放
- 后台任务（BackgroundTasks）+ 前端进度轮询
- 帧分析结果时间轴展示
- **验收：** 上传视频 → 分析 → 时间轴标注鸟种

### Phase 4：照片整理（1 周）
- 重复/相似照片检测（pHash + SHA256）
- 鸟种符号链接目录自动生成
- 批量 EXIF 写入（鸟种名 → Title）
- **验收：** 去重检出、鸟种目录生成、EXIF 写入无乱码

### Phase 5：连拍 + 合成视频（1-2 周）
- 连拍检测 + 组内评分排序（复用 `burst_detector.py`，间隔 ≤ 250ms）
- 连拍照片批量识别（YOLO + BirdID）
- FFmpeg 连拍合成 MP4（可配置帧率/分辨率/每帧时长）
- 合成视频预览和下载
- **验收：** 连拍识别成功，合成视频播放流畅