# SuperPicky RAW 自动调色技术设计

> 生成日期: 2026-04-12
> 适用范围: bird-gallery-web 单张 RAW 编辑与批处理自动调色
> 目标: 在不破坏现有识别、筛图、批处理能力的前提下，为 Sony ARW 等 RAW 文件提供接近 Lightroom Auto 风格的自动调色与手动微调能力。

---

## 1. 设计目标

### 1.1 业务目标

- 支持单张 RAW 照片的自动调色与手动调色。
- 自动调色第一版优先保证稳定、自然、可批量复用，不追求一步到位完全复刻 Lightroom Auto。
- 后续通过参数预测或外部引擎桥接，逐步逼近 Lightroom Auto 的观感。
- 单张编辑与未来批量能力复用同一套参数模型和渲染服务，避免两套逻辑分叉。

### 1.2 非目标

- 不在第一期实现完整的 Lightroom / Capture One 级局部蒙版系统。
- 不在第一期实现曲线点编辑、HSL 八色精修、局部笔刷。
- 不将图库页改造成复杂编辑器；编辑入口应放在单张详情页。

### 1.3 成功标准

- 用户可在照片详情页进入 RAW 编辑模式，查看自动调色结果并继续微调。
- 调色参数以“草稿 + 已保存版本”方式非破坏式存储，可重复渲染、可回退、可导出。
- 未来如需批量自动调色，应直接复用统一自动调色服务，而不是再实现另一套自动增强。
- 对同一张 ARW 的自动调色结果在多次执行中稳定一致。

---

## 2. 现状与问题

### 2.1 现有可复用基础

bird-gallery-web 已具备以下基础能力:

- backend/services/pureraw_service.py
  - 已有 DxO PureRAW 6 自动化能力，可作为高质量降噪 / 去马赛克外部引擎的集成基础。
- Python venv + rawpy
  - 项目 venv 已安装 rawpy 0.26.1，可用作 MVP 渲染底座。
  - 当前环境已确认支持 output_bps=16、no_auto_bright、gamma、use_camera_wb 等关键参数。
- frontend/src/views/PhotoDetailView.vue
  - 已有单张照片沉浸式详情页，适合作为编辑器入口。

### 2.2 现有不足

- backend/services/thumbnail_generator.py 主要服务于缩略图与识别预览:
  - 优先提取嵌入 JPEG 或 preview.jpg。
  - rawpy 仅作为预览级回退。
  - 这条链路不适合承载高保真 RAW 显影。
- backend/api/photos.py 中 RAW 识别也优先使用 preview.jpg 缓存。
- 当前数据库缺少单张照片编辑版本与参数存储模型。
- 现有批处理相关功能问题较多，实际不可作为新方案基础:
  - batch_process_service 的自动调色依赖旧流程和外部人工环节。
  - 现有 batch_process_items / batch_schemas 设计服务于旧批处理任务，不适合作为单张编辑模型继续扩展。
  - 建议将现有批处理实现视为遗留功能，冻结并逐步废弃，而不是继续复用或叠加新逻辑。

### 2.3 核心判断

如果目标是接近 Lightroom Auto，不能基于 preview.jpg、PIL、直方图均衡这类已烘焙图像增强方案去做。必须建立单独的 RAW 显影链路，至少满足以下条件:

- 使用 RAW 原始数据而非嵌入预览图。
- 使用线性或高位深中间表示进行调色决策。
- 参数可持久化，可重新渲染。
- 新能力不依赖现有批处理模块。
- 后续如需批量调色，应基于新的单张编辑内核重新编排，而不是继续改造旧批处理流程。

---

## 3. 总体方案

### 3.1 总体思路

新增一套面向 RAW 编辑的非破坏式显影服务，作为 bird-gallery-web 内的独立能力层。该能力层与现有识别、缩略图、旧批处理逻辑完全解耦，优先服务单张编辑场景；未来如需批量能力，应由新的批量编排层调用。

整体分为四层:

1. RAW 解码层
   - 负责读取 ARW/CR3/NEF 等 RAW 文件，生成高位深中间表示。
2. 调色参数层
  - 负责存储自动调色参数、用户手动调整参数、草稿状态、已保存版本信息。
3. 渲染层
   - 负责根据参数生成预览图和导出图。
4. 编排层
  - 负责详情页交互、后台任务、缓存管理，以及未来新的批量编排接入。
  - 负责同步 / 异步预览渲染切换策略。
  - 负责草稿状态、版本状态与缓存失效判定。

### 3.2 推荐阶段化路线

#### 路线 A: 内置 MVP

目标是先做可控、稳定、可批量复用的内置自动调色:

- RAW 解码: rawpy
- 参数模型: 曝光、对比、高光、阴影、白场、黑场、色温、色调、自然饱和度、饱和度
- 预览渲染: 后端生成 JPEG 预览
- 导出渲染: 后端生成 16 bit TIFF 或高质量 JPEG
- 自动调色策略: 规则型算法

#### 路线 B: 外部高质量引擎增强

目标是进一步逼近 Lightroom / ACR 的输出质量:

- 继续利用 DxO PureRAW 做去噪 / 光学修正 / 更优 demosaic
- 或桥接 Lightroom / Camera Raw / darktable 输出高质量基准结果
- 将外部结果映射回内部参数或作为 teacher 数据

#### 路线 C: LR 风格拟合

目标是逼近 Lightroom Auto 决策风格:

- 收集 Sony ARW 样本
- 记录 LR Auto 的输出图或 sidecar 参数
- 训练参数预测器，将 RAW 统计特征映射为内部调色参数

---

## 4. 架构设计

### 4.1 新增模块

建议新增以下后端模块:

- backend/services/raw_develop_service.py
  - 统一封装 RAW 解码、参数应用、预览渲染、导出渲染。
- backend/services/auto_tone_service.py
  - 负责自动调色参数生成。
- backend/services/photo_edit_service.py
  - 负责单张编辑版本创建、更新、查询、回滚。
- backend/api/photo_edits.py
  - 提供单张编辑相关 API。

### 4.2 与现有模块的关系

- thumbnail_generator.py
  - 继续负责缩略图和识别预览，不承载编辑显影逻辑。
- 旧 batch_process_service
  - 视为 legacy，不作为新方案依赖对象。
- PhotoDetailView.vue
  - 增加 RAW 编辑面板、自动调色入口、版本与导出入口。

### 4.3 逻辑边界

- 识别链路继续读取 preview.jpg 或普通缩略图，不与编辑预览共享缓存目录。
- 编辑链路使用独立缓存，避免影响识别稳定性和性能。
- 未来新的批量编排层如有需要，只调用编辑服务的参数与导出能力，不依赖前端状态。

---

## 5. 数据模型设计

### 5.1 新增数据表

为避免“草稿覆盖”和“版本保存”相互污染，建议将草稿态与已保存版本显式分离。

建议新增 photo_edit_versions 表与 photo_edit_drafts 表。

```sql
CREATE TABLE IF NOT EXISTS photo_edit_versions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id        TEXT NOT NULL,
    source_type     TEXT NOT NULL DEFAULT 'raw',
    version_no      INTEGER NOT NULL,
  is_current      INTEGER NOT NULL DEFAULT 0,
    is_auto_tone    INTEGER NOT NULL DEFAULT 0,
    base_version_id INTEGER,
    params_json     TEXT NOT NULL,
  params_hash     TEXT NOT NULL,
    render_status   TEXT NOT NULL DEFAULT 'ready',
    preview_path    TEXT,
    export_path     TEXT,
    histogram_json  TEXT,
    engine          TEXT,
    engine_version  TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photo_id) REFERENCES photos(id),
    FOREIGN KEY (base_version_id) REFERENCES photo_edit_versions(id),
    UNIQUE(photo_id, version_no)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_photo_edit_current
ON photo_edit_versions(photo_id, is_current)
WHERE is_current = 1;

CREATE TABLE IF NOT EXISTS photo_edit_drafts (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  photo_id        TEXT NOT NULL UNIQUE,
  base_version_id INTEGER,
  params_json     TEXT NOT NULL,
  params_hash     TEXT NOT NULL,
  render_revision INTEGER NOT NULL DEFAULT 0,
  preview_path    TEXT,
  histogram_json  TEXT,
  render_status   TEXT NOT NULL DEFAULT 'idle',
  last_task_id    TEXT,
  engine          TEXT,
  engine_version  TEXT,
  created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (photo_id) REFERENCES photos(id),
  FOREIGN KEY (base_version_id) REFERENCES photo_edit_versions(id),
  FOREIGN KEY (last_task_id) REFERENCES tasks(id)
);
```

  说明:

  - `UNIQUE(photo_id, version_no)` 用于防止并发或异常状态下版本号重复。
  - `idx_photo_edit_current` 依赖 SQLite partial index，要求 SQLite >= 3.8.0。
  - 如果运行环境无法保证 SQLite 版本，应改为应用层维护当前版本唯一性。
- `photo_edit_versions` 只存已保存、不可变的版本。
- `photo_edit_drafts` 每张照片最多一条，用于承载正在编辑的草稿状态。
- `params_hash` 用于缓存命中判断，`render_revision` 用于区分草稿多次渲染结果。

### 5.2 参数 JSON 结构

```json
{
  "exposure": 0.35,
  "contrast": 8,
  "highlights": -28,
  "shadows": 34,
  "whites": 12,
  "blacks": -10,
  "temperature": 5200,
  "tint": 6,
  "vibrance": 18,
  "saturation": 4,
  "tone_curve": null,
  "schema_version": 1
}
```

### 5.3 字段说明

- source_type
  - 标记版本来源，初期可固定为 raw。
- is_current
  - 仅用于已保存版本，表示当前选中的正式版本。
- is_auto_tone
  - 标记是否由自动调色生成。
- base_version_id
  - 草稿或新版本基于哪个已保存版本继续编辑。
- params_hash
  - 用于判断参数是否变化，并参与缓存键计算。
- histogram_json
  - 可缓存 RGB 或亮度直方图，减少重复计算。
- last_task_id
  - 草稿最近一次异步预览渲染对应的任务 id。
- engine / engine_version
  - 用于标记渲染引擎来源，便于升级后做兼容判断。
- schema_version
  - 表示 params_json 的结构版本，不等同于 version_no。
- render_revision
  - 草稿每次有效参数变更或强制重渲染时递增，用于预览缓存失效和并发响应去重。

---

## 6. 参数模型

### 6.1 第一版参数范围

建议第一版仅开放以下参数:

- exposure: -4.0 到 +4.0 EV
- contrast: -100 到 +100
- highlights: -100 到 +100
- shadows: -100 到 +100
- whites: -100 到 +100
- blacks: -100 到 +100
- temperature: 2000 到 12000
- tint: -150 到 +150
- vibrance: -100 到 +100
- saturation: -100 到 +100

### 6.2 暂不开放的参数

第一期先不开放:

- HSL 分色
- 去朦胧
- 清晰度
- 颗粒
- 镜头校正手动参数
- 局部蒙版
- 曲线点编辑

这些参数要么 UI 成本高，要么和 LR Auto 的核心差距关系不大。

### 6.3 内部参数规范化

建议内部统一采用规范化参数模型，避免 UI 值直接等于渲染引擎值。示例:

- exposure 使用 EV 浮点
- temperature 使用 Kelvin
- contrast / highlights / shadows 使用 -100 到 +100

这样后续替换 rawpy 渲染、外部引擎映射、模型输出都更稳定。

### 6.4 参数到渲染操作的映射层

第一版必须明确一点：rawpy 不直接提供 `highlights=-28`、`shadows=34` 这类 Lightroom 风格参数接口。

因此本方案需要新增一层参数映射逻辑，将统一参数模型转换为实际渲染操作。建议首版采用以下映射规则:

- exposure
  - 在线性 RGB 域中做全局曝光缩放，形式为 `rgb_linear *= 2 ** exposure_ev`。
- temperature / tint
  - 通过白平衡乘子或 RGB 通道增益在早期阶段修正，不在最终 sRGB 图上硬做偏色。
- highlights / shadows / whites / blacks
  - 基于亮度的分段 tone curve 处理。
  - highlights 主要压缩高亮区，shadows 主要抬升暗部区。
  - whites / blacks 用于控制端点白场和黑场。
- contrast
  - 在基础 tone map 之后施加中间调 S 曲线。
- vibrance
  - 对低饱和区域施加更高增益，对高饱和区域增益受限。
- saturation
  - 作为全局色度缩放，不替代 vibrance。

这层映射是第一版实现中的核心工作，不应被视为“rawpy 自带能力”。

---

## 7. 渲染链路设计

### 7.1 原则

- 预览图与导出图必须共享同一套参数解释逻辑。
- 预览可以降采样，但不能改变参数语义。
- 渲染结果应缓存，参数不变时避免重复显影。
- 第一版固定采用线性输出方案，而不是让 rawpy 直接输出带默认 gamma 和自动提亮的 sRGB 图。

### 7.2 关键技术决策

第一版明确选择以下方案:

- 采用方案 A：rawpy 负责 demosaic 和基础 RAW 解码，输出线性 16 bit 中间表示。
- 不采用方案 B：让 rawpy 直接输出默认 sRGB 图后再做二次调整。

推荐参数方向:

- `output_bps=16`
- `no_auto_bright=True`
- `gamma=(1, 1)`
- `use_camera_wb=True` 作为默认基线
- 预览阶段允许 `half_size=True`

原因:

- 这样可以保留更多高光和阴影调整空间。
- 参数语义更稳定，便于与未来外部引擎或 ML 预测结果对齐。
- 后续可以在统一的线性域内实现 tone curve 和色彩映射。

代价:

- 需要自己实现 tone mapping、contrast、highlights、shadows 等逻辑。
- 开发成本高于简单的“rawpy 出图后再用 PIL 修图”。

### 7.3 建议流程

```text
RAW 文件
  -> rawpy 线性 16 bit 解码
  -> 生成中间线性 RGB 表示
  -> 应用白平衡与基础曝光修正
  -> 应用分段 tone curve（highlights / shadows / whites / blacks）
  -> 应用 contrast 与色彩增强参数
  -> 应用输出 gamma 与色彩空间映射
  -> 生成预览 JPEG 或导出 TIFF/JPEG
```

### 7.4 预览渲染

预览渲染需求:

- 默认长边 1600 到 2048
- JPEG 质量 90
- 返回渲染版本号或缓存 key
- 参数不变时直接命中缓存

预览阶段建议:

- 使用 `half_size=True` 降低 demosaic 成本。
- 预分析和拖动过程优先走较小预览尺寸。
- 最终导出时再走全尺寸解码与渲染。

缓存路径建议:

- 已保存版本: data/photo_edits/{photo_id}/versions/{version_no}/preview.jpg
- 草稿预览: data/photo_edits/{photo_id}/draft/{engine_version}/{render_revision}_{params_hash}_{preview_size}.jpg

### 7.5 导出渲染

导出渲染需求:

- 支持 16 bit TIFF
- 支持高质量 JPEG
- 保留 EXIF 基础信息
- 可选写入 XMP 标记，说明导出来源为 SuperPicky RAW Edit

导出路径建议:

- data/photo_edits/{photo_id}/versions/{version_no}/export.tif
- data/photo_edits/{photo_id}/versions/{version_no}/export.jpg

### 7.6 rawpy 使用建议

rawpy 适合作为第一版内置方案，但要明确局限:

- 优点
  - 部署简单
  - 支持常见 RAW
  - 足以做 MVP
  - 当前项目环境已确认可直接使用
- 局限
  - 与 Adobe Camera Raw 的色彩和高光恢复仍有差距
  - 对不同相机 profile 的表现不如 LR 稳定

因此 rawpy 适合作为 MVP 渲染层，不应被宣传为“等同 LR 显影”。

---

## 8. 自动调色算法设计

### 8.1 V1: 规则型自动调色

V1 目标不是模仿 LR 参数，而是得到自然、稳定、可批量复用的结果。

输入特征建议包括:

- 亮度分布分位点
- 高光裁剪比例
- 阴影堵塞比例
- RGB 通道均值 / 中位数 / 分位点
- 饱和度分布
- RAW 统计信息
- EXIF: ISO、曝光时间、机身型号、镜头信息

输出参数:

- exposure
- highlights
- shadows
- whites
- blacks
- temperature
- tint
- vibrance

规则示例:

- 中灰偏低且高光安全时，提高 exposure。
- 高光裁剪比例高时，优先压 highlights 与 whites，而不是继续提曝光。
- 阴影堵塞严重时，提高 shadows，但限制 blacks 回拉幅度，避免灰雾感。
- RGB 通道整体偏蓝或偏绿时，微调 temperature / tint。
- 已高饱和场景优先调 vibrance，限制 saturation。

建议第一版至少将规则落为可执行的阈值逻辑。示例伪代码:

```text
luma = normalized_luminance(linear_rgb)
median_luma = percentile(luma, 50)
p95_luma = percentile(luma, 95)
highlight_clip_ratio = mean(luma > 0.98)
shadow_block_ratio = mean(luma < 0.02)

if median_luma < 0.18 and highlight_clip_ratio < 0.005:
  exposure += clamp((0.18 - median_luma) * 4.0, 0.0, 1.25)

if highlight_clip_ratio > 0.01:
  highlights -= clamp(highlight_clip_ratio * 4000, 10, 70)
  whites -= clamp(highlight_clip_ratio * 2500, 5, 40)

if shadow_block_ratio > 0.08:
  shadows += clamp(shadow_block_ratio * 500, 10, 45)
  blacks += clamp(shadow_block_ratio * 120, 0, 12)
```

上面的阈值不是最终答案，但必须有这一层量化逻辑，避免算法设计停留在自然语言层面。

### 8.2 V2: 样本拟合型自动调色

当 V1 跑稳后，再做更接近 LR Auto 的版本。

数据构建方式:

- 采集一批 Sony ARW 样本。
- 在 Lightroom 中执行 Auto。
- 记录:
  - XMP / sidecar 参数，或
  - LR 导出结果图
- 将 RAW 特征映射到内部参数模型。

模型形式建议从简单到复杂:

- 线性回归 / GBDT
- 小型 MLP
- 基于场景分类的参数模板

目标不是逐像素复刻 LR，而是逼近用户感知上的决策风格:

- 逆光时更稳地保高光
- 阴天鸟片更自然地提层次
- 绿背景场景不过度脏色

### 8.3 V3: 外部 teacher + 内部 student

长期可采用 teacher-student 思路:

- teacher: Lightroom / ACR / DxO / darktable 高质量输出
- student: SuperPicky 内部参数预测器

这样既保留内置能力，又能持续贴近外部引擎的审美决策。

---

## 9. API 设计

### 9.1 单张编辑查询

`GET /api/photo-edits/{photo_id}`

返回内容:

- 当前已保存版本信息
- 当前草稿信息
- 版本列表摘要
- 是否 RAW
- 是否已有自动调色结果

其中当前已保存版本信息至少应包含:

- version_id
- version_no
- preview_url
- is_auto_tone
- engine
- engine_version

其中当前草稿信息至少应包含:

- draft_id
- params_json
- params_hash
- render_revision
- render_status
- preview_url
- last_task_id
- engine
- engine_version

补充约束:

- 第一版每张照片严格只有一条草稿记录，不支持多草稿并存。
- `GET /api/photo-edits/{photo_id}` 是前端的单一状态真源；提交保存、丢弃草稿、切换历史版本、异步预览任务完成后，前端都应重新请求该接口对齐状态。

### 9.2 创建或刷新草稿自动调色

`POST /api/photo-edits/{photo_id}/draft/auto-tone`

请求体:

```json
{
  "engine": "internal_v1",
  "base_version_id": null,
  "force_recompute": false
}
```

返回内容:

- draft_id
- params_json
- render_revision

说明:

- 如果当前照片已有草稿，则覆盖草稿参数并重置其渲染状态。
- 如果没有草稿，则基于 base_version_id 或当前版本创建新草稿。

### 9.3 更新草稿参数

`PATCH /api/photo-edits/{photo_id}/draft`

请求体:

```json
{
  "params": {
    "exposure": 0.4,
    "highlights": -35,
    "shadows": 30
  }
}
```

返回内容:

- draft_id
- params_json
- params_hash
- render_revision
- draft_updated_at

说明:

- 第一版仅实现草稿覆盖模式，避免每次拖动滑杆都生成新版本。
- 草稿参数一旦变化，应更新 params_hash，并在需要时递增 render_revision。

### 9.4 保存版本

`POST /api/photo-edits/{photo_id}/draft/commit`

请求体:

```json
{
  "set_current": true
}
```

返回内容:

- version_id
- version_no
- version_preview_url
- current_version_changed
- draft_rebased

说明:

- 该接口将当前草稿固化为新的不可变版本。
- 第一版不支持自定义版本标题，避免引入未建模字段。
- 成功保存后，草稿保留，并自动将 `base_version_id` 更新为新保存的 `version_id`。
- 保存后草稿参数与新版本保持一致，后续继续编辑时从新版本继续增量修改。
- 返回中的 `version_preview_url` 仅表示新保存版本的正式预览，不承担草稿预览语义。
- 提交成功后，前端仍应重新调用 `GET /api/photo-edits/{photo_id}` 获取最新草稿详情，而不是假定草稿预览与保存版本预览完全共用同一地址。

### 9.5 预览渲染

`POST /api/photo-edits/{photo_id}/draft/render-preview`

请求体:

```json
{
  "preview_size": 1600,
  "quality": 90,
  "force_recompute": false
}
```

返回内容:

- status
- preview_url
- histogram
- task_id
- render_mode
- render_time_ms
- render_revision

说明:

- 参数更新与预览渲染分离，便于控制同步 / 异步策略。
- 后续如果需要切换预览尺寸或仅重刷缓存，无需重复提交 params。
- 当 `status=ready` 时，`preview_url` 必须可直接访问。
- 当 `status=pending` 时，必须返回 `task_id` 与当前 `render_revision`，前端据此轮询或忽略过期结果。
- 异步预览任务复用现有通用任务查询接口 `GET /api/tasks/{task_id}`。
- 当前项目已有该接口，前端不需要为预览任务新增专用轮询协议。
- 当任务状态变为 `done` 后，前端应重新调用 `GET /api/photo-edits/{photo_id}` 获取最新草稿详情与 `preview_url`。

统一响应契约建议:

```json
{
  "status": "ready",
  "preview_url": "/api/photo-edits/xxx/draft/preview?render_revision=12&preview_size=1600",
  "histogram": null,
  "task_id": null,
  "render_mode": "sync",
  "render_time_ms": 183,
  "render_revision": 12
}
```

异步时:

```json
{
  "status": "pending",
  "preview_url": null,
  "histogram": null,
  "task_id": "task_xxx",
  "render_mode": "async",
  "render_time_ms": null,
  "render_revision": 13
}
```

### 9.6 读取草稿预览

`GET /api/photo-edits/{photo_id}/draft/preview?render_revision=12&preview_size=1600`

返回内容:

- 图片二进制流，第一版可固定为 `image/jpeg`

说明:

- `render_revision` 必须由后端生成并回传，前端只消费，不自行拼接或猜测。
- 草稿预览 URL 应显式绑定 `render_revision` 与 `preview_size`，避免新旧渲染结果串用。
- 若请求的草稿 revision 已被淘汰或缓存文件不存在，后端返回 404；前端随后重新请求 `GET /api/photo-edits/{photo_id}` 获取当前有效预览地址。

### 9.7 读取已保存版本预览

`GET /api/photo-edits/{photo_id}/versions/{version_id}/preview?preview_size=1600`

返回内容:

- 图片二进制流，第一版可固定为 `image/jpeg`

说明:

- 已保存版本预览是版本语义下的稳定读取地址，可用于历史列表、对比视图和保存完成后的即时展示。
- 若缓存未命中，后端可同步补生成，但对前端保持同一读取契约，不额外暴露内部缓存细节。

### 9.8 丢弃草稿

`POST /api/photo-edits/{photo_id}/draft/discard`

返回内容:

- draft_id
- base_version_id
- params_json
- render_revision
- preview_url

说明:

- 由于第一版每张照片只有一条草稿，所谓“丢弃草稿”本质上是把唯一草稿重置到当前正式版本，而不是物理删除草稿行。
- 该操作应清除当前未保存修改，并将草稿的 `base_version_id` 对齐到当前正式版本。
- 若当前正式版本没有现成预览缓存，可返回 `preview_url=null`，由前端后续触发 `render-preview`。

### 9.9 切换当前版本 / 历史回退

`POST /api/photo-edits/{photo_id}/versions/{version_id}/activate`

返回内容:

- current_version_id
- current_version_preview_url
- draft_id
- draft_reset

说明:

- 该接口用于把指定已保存版本设为当前正式版本，并作为第一版唯一支持的历史回退方式。
- 为避免当前版本与唯一草稿长期分叉，接口成功后必须同步将草稿重置到该版本参数，等价于“切换当前版本并丢弃草稿未保存修改”。
- 第一版不提供“只切 current、不动 draft”的模式，避免状态机复杂化。
- 前端在该接口成功后应重新请求 `GET /api/photo-edits/{photo_id}`，不要依赖本接口返回值自行拼装完整状态。

### 9.10 导出

`POST /api/photo-edits/{photo_id}/versions/{version_id}/export`

请求体:

```json
{
  "format": "tiff",
  "quality": 95,
  "write_xmp": true
}
```

返回内容:

- task_id
- status

### 9.11 未来批量能力接入

`POST /api/batch-process/start`

不建议沿用现有旧批处理接口。未来如果需要批量自动调色，应新增独立批量 API，由新的批量编排层调用 auto_tone_service / raw_develop_service。

---

## 10. 前端交互设计

### 10.1 入口

入口放在 PhotoDetailView.vue，不放在 GalleryView.vue。

建议新增操作区:

- 自动调色
- 重置
- 丢弃修改
- 保存版本
- 版本历史
- 导出
- 与原图对比

### 10.2 编辑面板

第一版面板建议只包含:

- 曝光
- 对比
- 高光
- 阴影
- 白色色阶
- 黑色色阶
- 色温
- 色调
- 自然饱和度
- 饱和度

交互要求:

- 参数变化后节流触发预览渲染
- 显示渲染中状态
- 支持一键恢复自动调色初始值
- 支持一键丢弃未保存修改并回到当前正式版本
- 支持原图 / 调色图快速切换
- 支持从版本历史中选择某个已保存版本作为当前正式版本
- 保留上一帧预览图，在新预览返回前显示 loading 遮罩
- 新请求发起时取消旧请求，或至少在前端丢弃过期响应
- 当后端渲染时间超过 500ms 时，显示明确的“正在重新渲染 RAW 预览”状态

### 10.3 状态管理

建议新增前端 store:

- frontend/src/stores/photoEditStore.ts

负责:

- 当前版本加载
- 当前草稿加载
- 丢弃草稿与历史版本切换
- 参数草稿态
- 预览渲染节流
- 预览请求取消与过期响应丢弃
- 复用现有通用任务轮询能力查询 `GET /api/tasks/{task_id}`
- 导出任务状态

### 10.4 与现有页面关系

- PhotoDetailView 负责单张编辑。
- 现有 BatchProcessView 视为 legacy，不作为本方案前置。
- GalleryView 不承担复杂编辑状态。

---

## 11. 任务流与缓存策略

### 11.1 单张预览任务

建议默认同步小任务 + 节流处理:

- 用户拖动滑杆
- 前端 200 到 300ms 节流提交
- 后端优先尝试快速渲染预览
- 返回新 preview_url

状态真源约束:

- `render-preview` 成功返回后可直接消费其 `preview_url`。
- `draft/commit`、`draft/discard`、`versions/{version_id}/activate` 成功后，前端必须重新请求 `GET /api/photo-edits/{photo_id}` 对齐完整状态。
- 异步预览任务完成后，同样以 `GET /api/photo-edits/{photo_id}` 返回内容为准，而不是沿用旧任务上下文里的临时字段。

建议明确切换策略:

- 预估耗时 < 500ms 时，走同步预览接口。
- 预估耗时 >= 500ms 或缓存未命中时，可切换为异步任务模式。
- 同步与异步两种模式都应返回统一的 preview_url / status 结构，避免前端分支复杂化。
- 前端收到异步任务结果时，只有当 `render_revision` 与当前草稿一致时才更新预览。
- 异步任务完成后，前端应重新拉取草稿详情，而不是依赖旧请求上下文自行拼接 `preview_url`。

### 11.2 导出任务

导出必须走异步任务系统，复用现有 tasks 表。

建议新增阶段:

- decode
- apply_params
- render
- write_metadata
- done

### 11.3 缓存键

预览缓存建议基于以下因素生成:

- photo_id
- draft_id 或 version_id
- params_hash
- render_revision
- engine_version
- preview_size

说明:

- 已保存版本是不可变的，因此可长期稳定缓存。
- 草稿缓存必须由 `params_hash` 或 `render_revision` 驱动失效，不能只依赖 version_id。
- 草稿新预览生成后，可覆盖旧草稿展示入口，但底层文件键建议带 revision，避免并发读写脏图。
- 草稿文件路径与缓存键必须保持一致，避免路径未变化但底层渲染算法或参数已变化造成脏缓存。
- 已保存版本预览地址与草稿预览地址必须保持语义分离，即便底层可复用同一渲染产物，也应通过不同资源路径暴露。

### 11.4 RAW 解码中间缓存

仅缓存最终 preview.jpg 不足以支撑拖滑杆体验。第一版还需要引入 RAW 解码中间缓存。

建议缓存内容:

- 线性 16 bit RGB 中间结果，或等价的 memory-mapped 中间文件
- 分为 preview decode 与 export decode 两种级别

缓存键建议包括:

- photo_id
- decode_profile（preview_half / export_full）
- engine_version

建议策略:

- 预览阶段优先复用 `half_size=True` 的中间解码结果
- 导出阶段使用全尺寸中间解码结果
- 使用 LRU 或总容量上限控制缓存，占用过高时自动淘汰
- 同一时刻仅保留最近一版草稿对应的热缓存，其余草稿中间结果优先淘汰

### 11.5 清理策略

- 仅保留每张照片最近 N 个版本的预览缓存
- 中间解码缓存按 LRU 和容量上限清理
- 导出文件默认长期保留
- 删除版本时同步清理 preview_path / export_path

### 11.6 异常与降级策略

必须定义以下异常场景的统一处理方式:

- RAW 解码失败
  - 返回明确错误码与错误信息。
  - 保留上一次成功预览，不清空前端画面。
- 预览渲染超时
  - 同步接口升级为异步任务，并返回 `status=pending`。
- 异步任务查询失败
  - 前端回退到重新请求 `GET /api/photo-edits/{photo_id}`，以当前草稿状态为准。
- 磁盘空间不足
  - 中止导出或缓存写入，并提示用户释放空间。
- 中间缓存损坏或丢失
  - 自动回退为重新解码，不让前端感知内部缓存错误。
- 后端重启导致任务丢失
  - 前端轮询超时后回退到重新请求草稿详情，避免永远等待。

---

## 12. 与现有批处理系统的关系

### 12.1 基本判断

现有 batch_process_service 不建议继续复用，也不应作为本方案的落地前提。

原因:

- 现有实现问题较多，维护成本高。
- 当前流程中存在外部人工步骤，无法形成稳定产品闭环。
- 旧模型以任务产物为中心，不适合承载单张非破坏式编辑。

因此，本方案采取以下策略:

- 不在现有 batch_process_service 上继续叠加新能力。
- 新的 RAW 编辑能力先独立完成单张闭环。
- 未来若需要批量自动调色，单独建设新的批量编排层，调用统一的 raw_develop_service 与 auto_tone_service。

### 12.2 对遗留批处理的处理建议

建议处理方式:

- 冻结现有 batch_process_service，不再继续扩展功能。
- 在文档和 UI 上标记为 legacy / 实验性，避免作为主路径宣传。
- 新功能不复用 batch_process_items、tone_output、auto_tone_tool 等旧设计。
- 当新的单张编辑内核稳定后，视业务需要新增独立的 batch_edit_tasks 或等价模型。

### 12.3 未来批量能力的设计原则

未来如果重新引入批量自动调色，建议遵循以下原则:

- 单张优先，批量复用单张核心服务。
- 批量任务只做队列、进度、失败重试与结果汇总，不重复实现调色逻辑。
- 批量参数模型直接复用单张参数模型。
- 外部引擎桥接仍作为可选 engine，而不是绑死在批处理路径里。

可能的 engine 仍可保留为:

- internal_v1
- darktable
- lightroom_bridge

但这些 engine 应挂接到新的统一编辑内核，而不是继续放在旧 batch_process_service 下。

### 12.4 兼容策略

第一期不要求立即删除旧批处理代码，但要避免继续扩大其职责。

做法:

- 停止在旧批处理代码上新增功能。
- 保留现有功能仅用于过渡或内部验证。
- 新的 RAW 自动调色开发不依赖旧批处理完成度。

这样可以避免新旧两条线继续相互污染。

---

## 13. 风险与权衡

### 13.1 质量风险

- rawpy 输出与 Adobe Camera Raw 仍有差距。
- 不同相机机型的色彩 profile 一致性不足。
- 仅靠规则型算法难以完全达到 LR Auto 风格。

应对方式:

- 对外明确命名为“自动调色”而不是“Lightroom 同款”。
- 通过样本拟合逐步逼近 LR 风格。
- 保留外部高质量引擎桥接能力。

### 13.2 性能风险

- RAW 解码和预览渲染成本显著高于缩略图。
- 高频参数拖动可能引发大量重复渲染。
- 如果缺少中间解码缓存，交互延迟会直接失控。

应对方式:

- 节流提交
- 预览分辨率限制
- 缓存命中
- 必要时后台 worker 化

### 13.3 复杂度风险

- 单张编辑、批处理、外部引擎桥接容易出现三套参数体系。

应对方式:

- 坚持统一参数模型
- 所有 engine 都向统一参数或统一输出契约收敛

### 13.4 交互一致性风险

- 草稿态、当前版本、异步预览任务三者容易出现状态错位。

应对方式:

- 明确“草稿”和“已保存版本”是两种不同实体。
- 预览更新必须携带 render_revision，前端只消费最新 revision。
- 保存版本后明确是否保留草稿，并保持 API 行为一致。

---

## 14. 实施计划

### Phase 0: 渲染基线验证

目标:

- 在正式开发前确认 rawpy 管线能达到可接受的画质基线

工作项:

- 选取 10 到 20 张典型 Sony ARW 样本
- 用 rawpy 线性 16 bit 输出生成基准图
- 实现最小 tone map 与 gamma 输出
- 与 Lightroom 默认输出、Lightroom Auto 输出进行目视对比
- 记录画质差距、主要偏色、主要高光恢复问题
- 输出验证 checklist：偏色程度、高光恢复、阴影层次、细节保留、耗时、内存占用

交付标准:

- 确认 rawpy 方案可作为 MVP 继续推进，或尽早转向更强外部引擎路线

### Phase 1: MVP 骨架

目标:

- 打通单张 RAW 自动调色最小闭环

工作项:

- 完成线性输出渲染路径与参数映射层
- 新增 photo_edit_versions 表
- 新增 photo_edit_drafts 表
- 新增 raw_develop_service.py
- 新增 auto_tone_service.py
- 新增 photo_edits API
- 新增 render-preview 独立接口
- 新增 draft commit 接口
- 在 PhotoDetailView 中增加编辑入口与基础滑杆
- 支持自动调色、草稿参数覆盖、预览刷新、导出
- 引入 preview / export 两级 RAW 解码缓存
- 明确 photoEditStore 与现有 taskStore 的职责边界

交付标准:

- Sony ARW 可完成自动调色和手动微调
- 可导出 TIFF/JPEG

### Phase 2: 新批量编排层

目标:

- 在不复用旧批处理实现的前提下，提供新的批量自动调色能力

工作项:

- 新增 batch edit task 模型或等价任务表
- 新建批量编排 API 与任务执行器
- 批量任务内部调用 raw_develop_service / auto_tone_service
- 补充任务进度、失败重试和结果记录

交付标准:

- 不依赖旧 batch_process_service 即可完成批量自动调色

### Phase 3: 质量增强

目标:

- 提升结果观感，缩小与 LR Auto 的差距

工作项:

- 引入更多 RAW 统计特征
- 相机机型差异化参数模板
- 样本拟合型参数预测

交付标准:

- 常见 Sony ARW 场景下自动结果明显优于 V1

### Phase 4: 外部高质量桥接

目标:

- 为高质量工作流提供增强路径

工作项:

- 优化 PureRAW 接入
- 增加 lightroom_bridge engine
- 打通 teacher-student 数据采样流程

---

## 15. 推荐开发顺序

推荐严格按以下顺序实施:

1. rawpy 渲染基线验证
2. 数据表与参数模型
3. 草稿 / 已保存版本模型
4. raw_develop_service MVP
5. 参数映射层
6. 预览缓存与异步契约
7. auto_tone_service V1
8. PhotoDetailView 单张编辑面板
9. 导出任务
10. 新批量编排层
11. 质量增强与外部桥接

理由:

- 先验证 rawpy 的画质基线，避免在错误渲染路线里投入大量实现成本。
- 先把草稿与已保存版本模型定清楚，避免实现阶段前后端状态机返工。
- 先把单张闭环跑通，最容易验证图像质量。
- 如果单张结果不成立，直接上批量能力只会放大问题。
- 参数模型先稳定，后续外部桥接和 ML 拟合才不会反复返工。

---

## 16. 最终建议

如果目标是尽快上线可用功能，建议采用以下决策:

- 编辑入口: PhotoDetailView
- 内置引擎: rawpy 线性 16 bit 输出 + 统一参数模型
- 自动调色 V1: 规则型算法
- 预览模式: 草稿实体 + 独立 render-preview 接口 + render_revision 去重
- 性能策略: preview / export 两级解码缓存 + 同步 / 异步渲染切换
- 旧批处理: 视为遗留实现，不作为新方案基础
- 批量能力: 在单张内核稳定后单独重建
- 高质量增强: 保留 PureRAW / darktable / Lightroom bridge 作为后续选项

这条路线的优势是:

- 与现有代码最兼容
- 可以快速形成单张与批量统一闭环
- 不会误把缩略图预览链路升级成错误的编辑引擎
- 为后续逼近 Lightroom Auto 保留清晰演进路径

这条路线的边界也要明确:

- 第一版不会达到 Adobe Camera Raw 同等级别的色彩与高光恢复。
- 若产品口径要强调“接近 LR Auto”，必须预留样本拟合或外部 teacher 方案，且不应宣称与 Lightroom Auto 原理或效果等同。
