# SuperPicky 项目架构文档

> 生成日期: 2026-04-04
> 项目版本: 从代码仓库自动分析

---

## 1. 项目概述

SuperPicky 是一款面向鸟类摄影师的 AI 选片工具，通过多维度 AI 检测（鸟类识别、关键点检测、飞行状态、美学评分等）自动对照片进行评分和筛选。

### 1.1 核心功能

- **YOLO 鸟类检测**: 检测鸟类位置和分割掩码
- **关键点检测**: 识别眼部/喙的位置和可见性
- **飞行状态检测**: 判断是否飞版
- **曝光检测**: 检测过曝/欠曝
- **对焦点检测**: 判断对焦是否在鸟上
- **美学评分**: TOPIQ 美学质量评估
- **综合评分**: 0-3 星评分体系
- **鸟类识别**: OSEA 鸟类种类识别

---

## 2. 目录结构

```
SuperPicky/
├── main.py                      # GUI 入口 (PySide6)
├── superpicky_cli.py           # CLI 入口
├── constants.py                 # 全局常量定义
├── config.py                    # 基础配置管理
├── advanced_config.py           # 高级配置管理
├── ai_model.py                  # YOLO11 鸟类检测模型
├── topiq_model.py               # TOPIQ 美学评分模型
├── iqa_scorer.py                # 图像质量评分
├── post_adjustment_engine.py    # 后期调整引擎
├── birdid_cli.py / birdid_server.py  # BirdID 服务
├── server_manager.py            # 服务器管理
├── requirements*.txt           # 依赖清单
├── SuperPicky.spec             # macOS PyInstaller 配置
├── SuperPicky_win64.spec       # Windows PyInstaller 配置
│
├── core/                        # 核心业务逻辑
│   ├── photo_processor.py       # 照片处理核心
│   ├── rating_engine.py         # 评分引擎
│   ├── keypoint_detector.py     # 关键点检测 (眼/喙)
│   ├── flight_detector.py        # 飞版检测
│   ├── exposure_detector.py      # 曝光检测
│   ├── focus_point_detector.py  # 对焦点检测
│   ├── burst_detector.py        # 连拍检测
│   ├── file_manager.py          # 文件管理
│   ├── config_manager.py        # 配置管理
│   └── ...
│
├── ui/                          # GUI 界面
│   ├── main_window.py           # 主窗口 (150KB+)
│   ├── thumbnail_grid.py        # 缩略图网格
│   ├── detail_panel.py          # 详情面板
│   ├── filter_panel.py          # 过滤面板
│   ├── results_browser_window.py # 结果浏览器
│   ├── fullscreen_viewer.py     # 全屏查看器
│   ├── birdid_dock.py           # 鸟类识别停靠面板
│   └── comparison_viewer.py     # 照片对比查看器
│
├── tools/                       # 工具模块
│   ├── exiftool_manager.py      # ExifTool 元数据写入
│   ├── report_db.py             # SQLite 报告数据库
│   ├── merged_report_db.py      # 合并报告数据库
│   ├── i18n.py                  # 国际化
│   ├── file_utils.py            # 文件工具
│   ├── system_logger.py         # 系统日志
│   ├── memory_monitor.py        # 内存监视
│   ├── patch_manager.py         # 补丁管理
│   └── update_checker.py       # 更新检查
│
├── birdid/                      # 鸟类识别模块
│   ├── bird_identifier.py       # 鸟类识别核心
│   ├── bird_database_manager.py # 鸟类数据库管理
│   ├── osea_classifier.py       # OSEA 分类器
│   ├── avonet_filter.py         # Avonet 过滤器
│   ├── ebird_country_filter.py  # eBird 区域过滤
│   └── data/                    # 鸟类数据
│       ├── bird_reference.sqlite
│       └── offline_ebird_data/  # 离线 eBird 数据
│
├── models/                      # AI 模型文件
│   ├── yolo11l-seg.pt           # YOLO 分割模型
│   ├── model20240824.pth       # OSEA 鸟类识别模型
│   ├── cub200_keypoint_resnet50_slim.pth  # 关键点检测模型
│   └── superFlier_efficientnet.pth         # 飞版检测模型
│
├── locales/                     # 国际化语言包
│   ├── en_US.json
│   └── zh_CN.json
│
├── app_user_stat/               # 遥测/统计
│   └── telemetry.py            # Countly 遥测
│
├── workflows/                   # 工作流文档
├── docs/                        # 文档
└── img/                         # 图标等资源
```

---

## 3. 核心处理流程

### 3.1 照片处理流程 (PhotoProcessor)

位于 `core/photo_processor.py`

```
照片输入 (目录)
    │
    ▼
┌─────────────────────────────────────────┐
│  1. 文件扫描                            │
│     - 识别 RAW/JPG/HEIF 文件           │
│     - RecursiveScanner 递归扫描         │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  2. RAW 转 JPEG                         │
│     - 使用 exiftool 转换为临时 JPEG      │
│     - find_bird_util.raw_to_jpeg         │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  3. YOLO 鸟类检测                        │
│     - ai_model.py                       │
│     - 检测鸟类位置和分割掩码             │
│     - 计算 AI 置信度                     │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  4. 关键点检测                           │
│     - core/keypoint_detector.py         │
│     - 检测左眼、右眼、喙的位置           │
│     - 计算可见性和头部区域锐度           │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  5. 飞行检测 [可选]                      │
│     - core/flight_detector.py           │
│     - EfficientNet-B3 判断飞行状态       │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  6. 曝光检测 [可选]                      │
│     - core/exposure_detector.py         │
│     - 检测过曝/欠曝                      │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  7. 对焦点检测 [可选]                    │
│     - core/focus_point_detector.py      │
│     - 提取相机对焦点坐标                 │
│     - 判断对焦是否在鸟上                 │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  8. 美学评分                            │
│     - topiq_model.py                    │
│     - TOPIQ 美学评分 (0-10)             │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  9. 综合评分                            │
│     - core/rating_engine.py             │
│     - 综合所有指标计算 0-3 星            │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  10. 元数据写入                          │
│      - tools/exiftool_manager.py        │
│      - 写入评分、标签、锐度等到 EXIF     │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  11. 文件整理                            │
│      - 按星级移动到对应文件夹            │
│      - 精选旗标处理                      │
└─────────────────────────────────────────┘
    │
    ▼
结果输出
```

### 3.2 评分规则 (RatingEngine)

位于 `core/rating_engine.py`

#### 评分等级

| 星级 | 名称 | 条件 | 代码常量 |
|------|------|------|----------|
| -1 | 拒片 (Rejected) | 无鸟 | REJECTED |
| 0 | 普通-问题片 | 最低标准不通过 | LEVEL_0 |
| 1 | 普通-合格 | 通过最低标准但锐度/美学都不达标 | LEVEL_1 |
| 2 | 良好 | 锐度 OR 美学达标 | LEVEL_2 |
| 3 | 优选 | 锐度 AND 美学双达标 | LEVEL_3 |

#### 精选旗标 (Pick)

- 在所有 3 星照片中，取锐度+美学综合排名前 25% 设为精选

#### 权重因素

| 因素 | 规则 |
|------|------|
| 眼睛可见度 | visibility < 0.5 时渐进式降星 |
| 对焦位置 | 头部 > SEG > BBox > 外部 |
| 飞版加成 | 锐度 x1.2, 美学 x1.1 |
| 曝光问题 | 降一星 |

---

## 4. 模块依赖关系

### 4.1 入口模块

| 文件 | 职责 |
|------|------|
| `main.py` | GUI 入口点，初始化 PySide6 应用、主窗口、错误日志、多进程处理 |
| `superpicky_cli.py` | CLI 入口点，支持 process/reset/restar/identify 等命令 |

### 4.2 模块依赖图

```
main.py (GUI入口)
  └─→ ui/main_window.py
        ├─→ core/photo_processor.py
        │     ├─→ ai_model.py (YOLO)
        │     ├─→ topiq_model.py (TOPIQ)
        │     ├─→ core/keypoint_detector.py
        │     ├─→ core/flight_detector.py
        │     ├─→ core/exposure_detector.py
        │     ├─→ core/focus_point_detector.py
        │     ├─→ core/rating_engine.py
        │     ├─→ tools/exiftool_manager.py
        │     └─→ tools/report_db.py
        │
        ├─→ birdid/bird_identifier.py
        │     └─→ birdid/bird_database_manager.py
        │
        ├─→ tools/i18n.py
        ├─→ tools/system_logger.py
        └─→ advanced_config.py
              └─→ config.py

superpicky_cli.py (CLI入口)
  └─→ core/photo_processor.py (同上)
```

### 4.3 配置系统层次

```
constants.py (常量)
  - APP_VERSION
  - RAW/JPG/HEIF 扩展名
  - 星级文件夹名称映射

config.py (基础配置)
  - 路径约定 (resource_path, get_app_config_dir)
  - 设备检测 (get_best_device)
  - 懒加载注册表 (get_lazy_registry)

advanced_config.py (高级配置)
  - 用户可配置的阈值和开关
  - 持久化到 JSON 文件
  - 评分参数、曝光阈值、连拍设置等
```

---

## 5. 核心模块详解

### 5.1 核心业务模块 (core/)

| 模块 | 文件 | 职责 |
|------|------|------|
| 照片处理核心 | `photo_processor.py` | 协调所有 AI 检测、评分、元数据写入、文件整理 |
| 评分引擎 | `rating_engine.py` | 根据锐度/美学/关键点可见性等计算 0-3 星评分 |
| 关键点检测 | `keypoint_detector.py` | 使用 ResNet50 检测鸟类左眼、右眼、喙的关键点 |
| 飞行检测 | `flight_detector.py` | 使用 EfficientNet-B3 判断鸟类是否处于飞行状态 |
| 曝光检测 | `exposure_detector.py` | 检测照片是否过曝/欠曝 |
| 对焦点检测 | `focus_point_detector.py` | 从 RAW 文件提取对焦点坐标，判断对焦位置 |
| 连拍检测 | `burst_detector.py` | 连拍检测与分组 |

### 5.2 AI 模型模块

| 模块 | 文件 | 职责 |
|------|------|------|
| YOLO 检测 | `ai_model.py` | YOLO11l-seg 分割模型加载和鸟类检测 |
| 美学评分 | `topiq_model.py` | TOPIQ 美学评分模型 (PyTorch) |
| 图像质量 | `iqa_scorer.py` | 图像质量评分计算 |

### 5.3 鸟类识别模块 (birdid/)

| 模块 | 文件 | 职责 |
|------|------|------|
| 鸟类识别核心 | `bird_identifier.py` | 使用 OSEA 模型进行鸟种分类 |
| 数据库管理 | `bird_database_manager.py` | 鸟类数据库管理 |
| OSEA 分类器 | `osea_classifier.py` | OSEA 鸟类分类器 |
| Avonet 过滤器 | `avonet_filter.py` | Avonet 过滤器 |
| eBird 区域过滤 | `ebird_country_filter.py` | 基于 eBird 的地区鸟种过滤 |

### 5.4 工具模块 (tools/)

| 模块 | 文件 | 职责 |
|------|------|------|
| ExifTool 管理 | `exiftool_manager.py` | ExifTool 封装，写入评分/标签到照片元数据 |
| 报告数据库 | `report_db.py` | SQLite 报告数据库，存储处理结果 |
| 合并报告 | `merged_report_db.py` | 合并报告数据库 |
| 国际化 | `i18n.py` | 国际化 (中/英文) |
| 文件工具 | `file_utils.py` | 文件操作工具 |
| 系统日志 | `system_logger.py` | 系统日志 |
| 内存监视 | `memory_monitor.py` | 内存监视器 |
| 补丁管理 | `patch_manager.py` | 在线补丁管理 |

### 5.5 UI 模块 (ui/)

| 模块 | 文件 | 职责 |
|------|------|------|
| 主窗口 | `main_window.py` | 主窗口，协调所有 UI 组件和工作线程 |
| 缩略图网格 | `thumbnail_grid.py` | 照片缩略图网格显示 |
| 详情面板 | `detail_panel.py` | 照片详情面板 |
| 过滤面板 | `filter_panel.py` | 过滤面板 (星级/标签过滤) |
| 结果浏览器 | `results_browser_window.py` | 结果浏览器窗口 |
| 全屏查看器 | `fullscreen_viewer.py` | 全屏照片查看器 |
| 鸟类识别面板 | `birdid_dock.py` | 鸟类识别结果停靠面板 |
| 对比查看器 | `comparison_viewer.py` | 照片对比查看器 |

---

## 6. 技术栈

### 6.1 核心技术栈

| 类别 | 技术 | 用途 |
|------|------|------|
| GUI 框架 | PySide6 (Qt6) | 跨平台 GUI |
| AI/ML | PyTorch | 深度学习模型推理 |
| YOLO | Ultralytics YOLO11 | 鸟类检测和分割 |
| 图像处理 | OpenCV (cv2), PIL | 图像预处理 |
| 数据库 | SQLite | 报告数据存储 |
| 元数据 | ExifTool | RAW/JPG 元数据读写 |
| 打包 | PyInstaller | 跨平台打包 |
| 国际化 | JSON 语言包 | 中/英文界面 |

### 6.2 AI 模型清单

| 模型 | 文件 | 架构 | 用途 |
|------|------|------|------|
| YOLO11l-seg | `models/yolo11l-seg.pt` | YOLO11 | 鸟类检测 + 分割掩码 |
| CUB-200 Keypoint | `models/cub200_keypoint_resnet50_slim.pth` | ResNet50 | 眼部/喙关键点检测 |
| SuperFlier | `models/superFlier_efficientnet.pth` | EfficientNet-B3 | 飞版检测 |
| OSEA BirdID | `models/model20240824.pth` | - | 鸟类种类识别 |
| TOPIQ | `topiq_model.py` | PyTorch | 美学评分 |

### 6.3 依赖文件

| 文件 | 用途 |
|------|------|
| `requirements.txt` | CPU 版本依赖 |
| `requirements_base.txt` | 基础依赖 |
| `requirements_cuda.txt` | CUDA GPU 版本 |
| `requirements_mac.txt` | macOS 特定依赖 |

---

## 7. 关键文件索引

| 功能 | 文件路径 |
|------|---------|
| GUI 入口 | `main.py` |
| CLI 入口 | `superpicky_cli.py` |
| 主窗口 | `ui/main_window.py` |
| 照片处理核心 | `core/photo_processor.py` |
| 评分引擎 | `core/rating_engine.py` |
| YOLO 检测 | `ai_model.py` |
| TOPIQ 美学 | `topiq_model.py` |
| 关键点检测 | `core/keypoint_detector.py` |
| 飞行检测 | `core/flight_detector.py` |
| 曝光检测 | `core/exposure_detector.py` |
| 对焦点检测 | `core/focus_point_detector.py` |
| 连拍检测 | `core/burst_detector.py` |
| 鸟类识别 | `birdid/bird_identifier.py` |
| ExifTool 管理 | `tools/exiftool_manager.py` |
| 报告数据库 | `tools/report_db.py` |
| 国际化 | `tools/i18n.py` |
| 基础配置 | `config.py` |
| 高级配置 | `advanced_config.py` |
| 常量定义 | `constants.py` |
| 遥测 | `app_user_stat/telemetry.py` |

---

## 8. 数据存储

### 8.1 报告数据库 (SQLite)

- 路径: `tools/report_db.py`
- 存储内容: 每张照片的处理结果、评分、标签等
- 多线程安全: 使用连接池或每线程连接

### 8.2 配置文件 (JSON)

- 高级配置持久化到 JSON 文件
- 路径: 通过 `config.py` 的 `get_app_config_dir()` 获取

### 8.3 元数据 (EXIF)

- 使用 ExifTool 写入评分、标签、锐度等到照片 EXIF
- 支持 RAW/JPG/HEIF 格式

---

## 9. 开发规范

参考 `scripts_dev/AI_CODING_RULES.md` 和 `.cursor/rules/superpicky-core-rules.mdc`：

- 使用 UTF-8，避免中文乱码
- ExifTool 非 ASCII 元数据写入使用 UTF-8 临时文件
- 保持 Windows + macOS 兼容性
- 多线程 SQLite 代码需序列化共享连接访问
- 严禁绕过 DB 封装器直接调用私有连接
- 保持事务处理同步和防御性
- 持久化进程需干净且幂等关闭
- CUDA 错误优先诊断打包/运行时问题
- Torch/CUDA Windows 打包保持 UPX 禁用
