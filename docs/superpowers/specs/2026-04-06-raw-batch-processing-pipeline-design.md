# RAW 照片批量处理管线设计

日期: 2026-04-06
状态: 设计稿 (review v2 — 修复 spec-review 发现的问题)

## 1. 目标

为 bird-gallery-web 新增 RAW 照片端到端批量处理能力：

输入一批 RAW 照片（如 Sony ARW），自动完成识别、评分、筛选、降噪、调色、智能裁切、水印叠加，最终输出可发布的 JPG。

### 1.1 处理流程总览

```
RAW (ARW)
  → Phase 1: 鸟种识别+评分 (现有管线复用)
  → Phase 2: 筛选 ≥ N★ (可配置, 默认2)
  → Phase 3: DxO PureRAW DeepPRIME XD3 降噪 → 输出 DNG
  → Phase 4: Lightroom Classic 自动调色 (autoTone) → 导出 TIFF
  → Phase 5: 智能裁切 (多方案) + 水印 (多方案) → 输出 JPG
  → Phase 6: 注册到 Web 图库 DB, 关联原始 RAW
```

### 1.2 设计约束

- 运行环境: macOS Apple Silicon (Mac Mini M4)
- 高质量优先, 速度可以牺牲
- PureRAW 6 和 Lightroom Classic 需在本机前台运行
- 不引入付费云端 API
- 遵守项目 CLAUDE.md 规则: UTF-8 安全、ExifTool 中文写入用 temp 文件、持久进程确定性清理

## 2. Phase 1 & 2: 识别、评分与筛选

### 2.1 复用现有管线

Web 后端已有完整的识别和评分流程:

1. 从 RAW 提取嵌入 JPEG (rawpy.extract_thumb 或 ExifTool -JpgFromRaw) 做推理输入
2. YOLO 鸟类检测 → 返回 `[x1, y1, x2, y2]` bbox (原图像素坐标)
3. 关键点检测 → 头部锐度 (Tenengrad)
4. TOPIQ 美学评分
5. RatingEngine 计算星级

### 2.2 检测框坐标空间说明

YOLO 检测在嵌入 JPEG 上执行, bbox 坐标为嵌入 JPEG 的像素坐标。但 `birdid/bird_identifier.py` 的 `detect_and_crop_bird` 方法返回的 bbox 已转换为**原始图像坐标**。存入 DB 的 `detection_box` 为原图坐标系。

Phase 5 裁切时, 目标图像为 PureRAW 输出的 DNG (全 RAW 分辨率)。由于 PureRAW 不改变分辨率, DNG 与原始 RAW 尺寸一致, 因此 bbox 坐标可直接用于裁切, 无需二次映射。

如果通过 Lightroom 导出为 TIFF/JPEG 且改变了尺寸, 则需要按比例缩放 bbox:
```python
scale_x = tiff_width / raw_width
scale_y = tiff_height / raw_height
bbox_scaled = [x1*scale_x, y1*scale_y, x2*scale_x, y2*scale_y]
```

### 2.2 星级标准 (现有)

| 星级 | 含义 | 判定条件 |
|------|------|----------|
| -1 | 拒绝 | 未检测到鸟 |
| 0 | 差 | 置信度<0.50 或 头部锐度<100 或 TOPIQ<3.5 |
| 1 | 一般 | 通过最低门槛但锐度和美学都未达标 |
| 2 | 良好 | 锐度≥400 或 TOPIQ≥5.0 (满足其一) |
| 3 | 优秀 | 锐度≥400 且 TOPIQ≥5.0 (同时满足) |

### 2.3 筛选

- 配置项: `min_rating`, 默认 2
- 仅将通过筛选的照片送入后续降噪/调色流程
- 优化点: 1000 张 RAW 可能只有 ~400 张通过, 节省 ~60% 降噪时间

## 3. Phase 3: DxO PureRAW 降噪

### 3.1 自动化方案

PureRAW 6 无 CLI 和 AppleScript 字典。通过以下方式实现全自动:

#### Step 1: 修改处理预设

**重要: 先备份原始预设, 处理完成/失败后恢复。**

```python
import shutil, json

PRESET_PATH = os.path.expanduser(
    "~/Library/DxO_Labs/DxO PureRAW 6/ProcessingPresets.json")

def setup_pureraw_preset(task_id, output_dir):
    # 备份原始预设
    backup_path = PRESET_PATH + f".backup_{task_id}"
    shutil.copy2(PRESET_PATH, backup_path)

    # 修改预设
    with open(PRESET_PATH, 'r') as f:
        presets = json.load(f)
    # 找到自定义预设 (id=10) 并更新输出目录
    for p in presets:
        if p.get("id") == 10:
            p["CustomDestinationFolderActivatedValue"] = True
            p["CustomDestinationFolderValue"] = output_dir
            break
    with open(PRESET_PATH, 'w') as f:
        json.dump(presets, f, ensure_ascii=False, indent=4)
    return backup_path

def restore_pureraw_preset(backup_path):
    if os.path.exists(backup_path):
        shutil.move(backup_path, PRESET_PATH)
```

直接写入 `~/Library/DxO_Labs/DxO PureRAW 6/ProcessingPresets.json`:

```json
{
    "ProcessingTypedValue": 5,
    "LuminanceValue": 40,
    "ChrominanceValue": 50,
    "CustomDestinationFolderActivatedValue": true,
    "CustomDestinationFolderValue": "/tmp/pureraw_batch_{task_id}",
    "DngOutputFormat": true,
    "JpegOutputFormat": false,
    "JpegQualitySavedValue": 90,
    "FileRenamingActivatedValue": true,
    "FileRenamingPatternValue": 2,
    "id": 10,
    "isCustom": true,
    "name": "自定义预设"
}
```

关键参数:
- `ProcessingTypedValue`: 3=DeepPRIME 3, 5=DeepPRIME XD3
- 输出 DNG (线性, 保留最大编辑空间供后续调色)
- 自定义输出目录, 每批任务独立

#### Step 2: 发送文件到 PureRAW

```python
subprocess.run(["open", "-a", "DxO PureRAW 6"] + arw_file_list)
```

PureRAW 基于 QtSingleApplication, 运行中的实例通过 local socket 接收文件路径。

#### Step 3: AppleScript UI Scripting

```applescript
tell application "System Events"
    tell process "PureRAWv6"
        -- 等待导入完成
        delay 2
        -- 全选
        keystroke "a" using command down
        -- 点击处理按钮 (需根据实际UI元素定位)
        -- click button "Process" of window 1
        -- 或选择预设后处理
    end tell
end tell
```

前提: 系统偏好设置 → 隐私与安全 → 辅助功能 中授权终端/Python。

#### Step 4: 监控输出

```python
import time
from pathlib import Path

def wait_for_pureraw(output_dir, expected_files, timeout=7200):
    """轮询等待 PureRAW 输出所有文件"""
    start = time.time()
    while time.time() - start < timeout:
        existing = list(Path(output_dir).glob("*-DxO_DeepPRIME*.dng"))
        if len(existing) >= len(expected_files):
            return [str(f) for f in existing]
        time.sleep(5)
    raise TimeoutError("PureRAW processing timeout")
```

### 3.2 输出

- 文件名格式: `{原始文件名}-DxO_DeepPRIME XD3.dng`
- 处理速度: ~12 秒/张 (Apple Neural Engine)
- 400 张 ≈ 80 分钟

### 3.3 回退方案

如果 UI Scripting 不稳定, 提供半自动模式:
1. 脚本自动导入文件到 PureRAW 并设置预设
2. 通知用户手动点击"处理"
3. 脚本自动监控输出目录等待完成

### 3.4 任务取消处理

PureRAW 处于外部 GUI, 取消行为:
- `wait_for_pureraw` 轮询循环中检查 DB 任务状态, 发现 cancelled 时立即中止等待
- 不强制关闭 PureRAW (让用户决定), 但标记任务为 cancelled
- 已输出的 DNG 文件保留在临时目录, 不进入后续流程
- PureRAW 预设文件恢复原始备份

### 3.5 并发控制

批处理任务为全局互斥: 同一时刻只允许一个 `batch_process` 类型任务处于 running 状态。提交新任务时检查:
```python
existing = db.execute(
    "SELECT id FROM tasks WHERE type='batch_process' AND status='running'"
).fetchone()
if existing:
    raise HTTPException(409, "已有批处理任务在执行中")
```

原因: PureRAW 和 LR 均为单实例 GUI 应用, 无法并行处理多批任务。

## 4. Phase 4: Lightroom Classic 自动调色

### 4.1 扩展现有 LR 插件

在 `SuperBirdIDPlugin.lrplugin/` 中新增 `AutoToneExport.lua`:

```lua
local LrApplication = import 'LrApplication'
local LrDevelopController = import 'LrDevelopController'
local LrTasks = import 'LrTasks'
local LrDialogs = import 'LrDialogs'
local LrProgressScope = import 'LrProgressScope'
local LrExportSession = import 'LrExportSession'

LrTasks.startAsyncTask(function()
    local catalog = LrApplication.activeCatalog()
    local photos = catalog:getTargetPhotos()

    if #photos == 0 then
        LrDialogs.message("SuperPicky", "请先选中要处理的照片", "warning")
        return
    end

    local progress = LrProgressScope({
        title = "SuperPicky - Auto Tone + Export"
    })
    progress:setCancelable(true)

    -- 逐张应用 Auto Tone
    for i, photo in ipairs(photos) do
        if progress:isCanceled() then break end
        progress:setPortionComplete(i-1, #photos)
        progress:setCaption(photo:getFormattedMetadata("fileName"))

        catalog:setSelectedPhotos(photo, {photo})
        LrDevelopController.revealPanel("adjustPanel")
        LrDevelopController.autoTone()

        LrTasks.yield()  -- 让 LR 响应
    end

    -- 批量导出
    -- 导出设置通过 LR 导出预设或 exportSettings 表配置
    progress:done()
    LrDialogs.message("SuperPicky",
        string.format("已完成 %d 张照片的自动调色", #photos), "info")
end)
```

在 `Info.lua` 中注册新菜单项:

```lua
LrLibraryMenuItems = {
    { title = "SuperPicky - Identify Current Photo", file = 'LibraryMenuItem.lua' },
    { title = "SuperPicky - Auto Tone + Export", file = 'AutoToneExport.lua' },
},
```

### 4.2 工作流程

1. 将 PureRAW 输出的 DNG 文件导入 LR Catalog
2. 选中所有 DNG
3. 通过菜单触发插件: 图库 → 增效工具 → SuperPicky - Auto Tone + Export
4. 插件逐张 autoTone() 后批量导出 TIFF/JPEG

### 4.3 LR 自动化触发方式

从 Web 后端触发 LR 插件操作:

```python
# 方案A: AppleScript 触发 LR 菜单
osascript = '''
tell application "Adobe Lightroom Classic"
    activate
end tell
tell application "System Events"
    tell process "Adobe Lightroom Classic"
        -- 导入 DNG 文件
        keystroke "i" using {shift down, command down}
        delay 1
        -- 触发插件菜单
        click menu item "SuperPicky - Auto Tone + Export" of menu "增效工具附加" of menu item "增效工具附加" of menu "图库"
    end tell
end tell
'''
```

### 4.4 输出

- 格式: TIFF 16-bit 或 JPEG 95%
- 如果直接导出 JPEG, 可跳过后续 TIFF 中间步骤

### 4.5 回退方案

如果 LR 不可用, 使用 darktable-cli:

```bash
brew install --cask darktable
darktable-cli input.dng output.tiff \
  --core --conf plugins/imageio/format/tiff/bps=16
```

darktable 默认 scene-referred 管线 (Filmic RGB + Exposure +0.7EV + Color Calibration) 可产出合理效果。

## 5. Phase 5: 智能裁切系统

### 5.1 三个可配置维度

每个维度独立选择, 互相组合:

**维度1: 宽高比**

| 值 | 比例 |
|----|------|
| `16:9` | 1.778 |
| `4:3` | 1.333 |
| `3:2` | 1.500 |
| `1:1` | 1.000 |
| `21:9` | 2.333 |
| `9:16` | 0.563 (竖版) |
| `original` | 保持原图比例 |

**维度2: 输出分辨率**

| 值 | 尺寸 | 说明 |
|----|------|------|
| `4k` | 3840×(按比例) | 默认 |
| `fhd` | 1920×(按比例) | 网页展示 |
| `original` | 不缩放 | 保留裁切后原始像素 |
| `custom` | 用户指定 WxH | 自由设定 |

**维度3: 构图模式**

| 值 | 鸟体占比 | 行为 |
|----|---------|------|
| `center` | ~40-60% | 鸟检测框中心 = 画面中心 |
| `rule-of-thirds` | ~30-50% | 鸟中心放在最近的三分法交叉点 |
| `tight` | ~70-85% | 紧贴鸟体, 仅留 30% 边距 |
| `environmental` | ~15-30% | 最大裁切面积, 保留环境 |

### 5.2 构图模式算法

#### center (鸟居中)

```
1. 按选定宽高比计算最大裁切框 (不超过原图)
2. 裁切框中心 = 鸟检测框中心
3. 边界 clamp: 裁切框不超出图片
4. 验证: 鸟检测框必须完全在裁切框内 (含 padding)
```

#### rule-of-thirds (三分法)

```
1. 按选定宽高比计算最大裁切框
2. 计算4个三分交叉点: (W/3, H/3), (2W/3, H/3), (W/3, 2H/3), (2W/3, 2H/3)
3. 选择使鸟最接近某个交叉点的裁切位置
4. 偏好上方两个交叉点 (鸟在上1/3更自然)
5. 边界 clamp + 鸟体完整性验证
```

#### tight (紧凑特写)

```
1. 裁切框 = 鸟检测框 × bird_padding (默认 1.3)
2. 按选定宽高比扩展裁切框 (保持鸟居中)
3. 如果扩展后超出原图, 取最大可用区域
4. 缩放到目标分辨率
```

#### environmental (环境留白)

```
1. 裁切框 = 按选定宽高比的最大可用区域 (几乎全图)
2. 在可能范围内将鸟偏移到画面中心
3. 不保证鸟占比, 优先保留环境
```

### 5.3 裁切预设

| 预设名 | ratio | resolution | composition | 用途 |
|--------|-------|------------|-------------|------|
| `4k_wallpaper` | 16:9 | 3840×2160 | environmental | 桌面壁纸 |
| `phone_wallpaper` | 9:16 | 2160×3840 | center | 手机锁屏 |
| `social_square` | 1:1 | 2160×2160 | center | 微信/Instagram |
| `bird_closeup` | 4:3 | 3840×2880 | tight | 鸟种图鉴 |
| `cinematic` | 21:9 | 3440×1440 | rule-of-thirds | 超宽屏壁纸 |
| `original_crop` | original | original | center | 保留最大画质 |

### 5.4 安全机制

- 鸟体完整性检查: 裁切后鸟检测框必须 100% 在画面内
- 如果选定构图导致鸟被裁切, 自动降级到 center 模式
- bird_padding 最小 1.2, 保证鸟体周围至少 10% 空间

## 6. Phase 5 (续): 水印系统

### 6.1 四种水印类型

#### 6.1.1 text (文字水印)

半透明文字叠加在画面角落。

参数:

| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `text` | string | `"© YourName"` | 水印文字 |
| `font` | string | PingFang SC 路径 | 字体文件 |
| `font_size` | int | 48 | 字号 (像素) |
| `color` | (R,G,B) | (255,255,255) | 文字颜色 |
| `opacity` | int 0-255 | 128 | 透明度 |
| `position` | string | `"bottom-right"` | 9宫格位置 |
| `margin` | int | 40 | 距边缘像素 |
| `shadow` | bool | true | 文字投影 |
| `shadow_color` | (R,G,B) | (0,0,0) | 投影颜色 |
| `shadow_offset` | int | 2 | 投影偏移 |

position 可选值: `top-left`, `top-center`, `top-right`, `center-left`, `center`, `center-right`, `bottom-left`, `bottom-center`, `bottom-right`

#### 6.1.2 image (Logo 图片水印)

半透明 PNG 图片叠加。

参数:

| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `logo_path` | string | — | PNG 文件路径 (支持透明通道) |
| `scale` | float | 0.1 | Logo 宽度占画面宽度比例 |
| `opacity` | int 0-255 | 180 | 透明度 |
| `position` | string | `"bottom-right"` | 9宫格位置 |
| `margin` | int | 40 | 距边缘像素 |

#### 6.1.3 tiled (满屏平铺水印)

旋转半透明文字/图案全图平铺, 用于防盗。

参数:

| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `text` | string | `"© YourName"` | 平铺文字 |
| `font_size` | int | 36 | 字号 |
| `opacity` | int 0-255 | 30 | 透明度 (建议很低) |
| `color` | (R,G,B) | (255,255,255) | 文字颜色 |
| `rotation` | int | -30 | 旋转角度 (度) |
| `spacing_x` | int | 300 | 水平间距 |
| `spacing_y` | int | 200 | 垂直间距 |

#### 6.1.4 info-bar (EXIF 信息条)

在照片底部 (或顶部) 添加纯色信息条, 展示鸟种名称、拍摄参数、版权信息。

信息条示例:

```
┌──────────────────────────────────────────────────┐
│                                                  │
│                   (照片内容)                      │
│                                                  │
├──────────────────────────────────────────────────┤
│  白鹡鸰 White Wagtail                            │
│  Sony ILCE-7M4 · FE 200-600mm · 382mm · f/6.3   │
│  1/2000s · ISO 800        © 2026 YourName        │
└──────────────────────────────────────────────────┘
```

参数:

| 名称 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `bar_position` | string | `"bottom"` | `bottom` 或 `top` |
| `bar_bg_color` | (R,G,B) | (20,20,20) | 背景颜色 |
| `bar_padding` | int | 24 | 内边距 |
| `bar_mode` | string | `"append"` | `append`=追加在画面外(改变总高度), `overlay`=覆盖画面底部像素(不改变尺寸) |
| `text_color` | (R,G,B) | (230,230,230) | 文字颜色 |
| `font` | string | PingFang SC | 字体 |
| `title_font_size` | int | 42 | 鸟种名字号 |
| `detail_font_size` | int | 28 | 参数行字号 |
| `show_species` | bool | true | 显示鸟种名 |
| `species_lang` | string | `"cn+en"` | `cn`, `en`, `cn+en`, `scientific` |
| `show_exif` | bool | true | 显示拍摄参数 |
| `exif_fields` | list | `["camera","lens","focal","aperture","shutter","iso"]` | 要显示的 EXIF 字段 |
| `show_copyright` | bool | true | 显示版权 |
| `copyright_text` | string | `"© 2026 YourName"` | 版权文字 |

信息条中的鸟种名和 EXIF 来源:
- 鸟种名: 从 `photo_birds` 表读取 (species_cn, species_en)
- EXIF: 从 `photo_metadata` 表读取 (camera_model, lens_model, focal_length, aperture, shutter_speed, iso)

### 6.2 水印组合

用户可叠加多个水印层, 按列表顺序依次应用:

```python
watermark_configs = [
    WatermarkConfig(type="info-bar", show_species=True, show_exif=True),
    WatermarkConfig(type="text", text="@my_bird_account", position="bottom-right"),
]
```

### 6.3 水印预设

| 预设 ID | 名称 | 组成 |
|---------|------|------|
| `simple_copyright` | 简约版权 | 文字: 右下角 `© Name` |
| `brand_logo` | 品牌Logo | 图片: 右下角 Logo 10% |
| `anti_theft` | 防盗水印 | 满屏平铺: 30° 旋转低透明度 |
| `bird_guide` | 鸟类图鉴 | 信息条: 鸟种+EXIF+版权 |
| `social_share` | 社交分享 | 信息条 + 文字@账号 |
| `none` | 无水印 | 不添加水印 |

## 7. 配置数据结构

### 7.1 批处理任务配置

使用 Pydantic BaseModel (与现有 schemas.py 一致):

```python
from pydantic import BaseModel, Field
from typing import Optional

class BatchProcessConfig(BaseModel):
    # --- 筛选 ---
    min_rating: int = 2                         # 0-3

    # --- 降噪 ---
    denoise_enabled: bool = True
    denoise_algorithm: str = "DeepPRIME_XD3"    # DeepPRIME_3 | DeepPRIME_XD3
    denoise_luminance: int = 40                 # 0-100
    denoise_chrominance: int = 50               # 0-100

    # --- 调色 ---
    auto_tone_enabled: bool = True
    auto_tone_tool: str = "lightroom"           # lightroom | darktable

    # --- 裁切 ---
    crop_preset: str = "4k_wallpaper"           # 预设ID 或 "custom"
    crop_config: Optional[CropConfig] = None  # preset=custom 时使用

    # --- 水印 ---
    watermark_preset: str = "simple_copyright"  # 预设ID 或 "custom"
    watermark_layers: Optional[list[WatermarkConfig]] = None  # preset=custom 时使用

    # --- 输出 ---
    output_format: str = "jpeg"                 # jpeg | tiff | png
    output_quality: int = 95                    # JPEG 质量
    output_dir: str = ""                        # 空=默认 data/exports/{task_id}/


class CropConfig(BaseModel):
    aspect_ratio: str = "16:9"
    output_size: Optional[tuple[int, int]] = (3840, 2160)  # None=不缩放, 始终为(width, height)
    composition: str = "center"                 # center|rule-of-thirds|tight|environmental
    bird_padding: float = Field(default=1.3, ge=1.2)  # 鸟体安全边距倍数, 最小1.2


class WatermarkConfig(BaseModel):
    type: str = "text"                          # text|image|tiled|info-bar

    # --- 通用 ---
    opacity: int = 128
    position: str = "bottom-right"
    margin: int = 40

    # --- text 专用 ---
    text: str = "© YourName"
    font: str = "/System/Library/Fonts/PingFang.ttc"
    font_size: int = 48
    color: tuple[int, int, int] = (255, 255, 255)
    shadow: bool = True
    shadow_color: tuple[int, int, int] = (0, 0, 0)
    shadow_offset: int = 2

    # --- image 专用 ---
    logo_path: Optional[str] = None
    logo_scale: float = 0.1

    # --- tiled 专用 ---
    rotation: int = -30
    spacing_x: int = 300
    spacing_y: int = 200

    # --- info-bar 专用 ---
    bar_position: str = "bottom"
    bar_bg_color: tuple[int, int, int] = (20, 20, 20)
    bar_padding: int = 24
    text_color: tuple[int, int, int] = (230, 230, 230)
    title_font_size: int = 42
    detail_font_size: int = 28
    show_species: bool = True
    species_lang: str = "cn+en"
    show_exif: bool = True
    exif_fields: Optional[list[str]] = None  # None=全部
    show_copyright: bool = True
    copyright_text: str = "© 2026 YourName"
```

### 7.2 持久化

配置存储在 `data/batch_process_config.json`, 用户上次使用的配置自动保存, 下次默认加载。

预设配置内置在代码中, 不可由用户修改; 自定义配置由用户保存。

## 8. Web API 设计

### 8.1 新增 API 端点

```
# 获取批处理配置选项 (预设列表、参数范围)
GET  /api/batch-process/options

# 提交批处理任务
POST /api/batch-process/start
Body: BatchProcessConfig (JSON)
Response: { "task_id": "xxx", "estimated_time_minutes": 150 }

# 任务进度 (复用现有 tasks 系统)
# current_phase/current_file 存储在 tasks.result_json 中, 不新增列
GET  /api/tasks/{task_id}
Response: { "status": "running", "progress": 45.2,
            "result_json": {
                "current_phase": "denoise",
                "current_file": "DSC09514.ARW",
                "phase_progress": { "detect": 100, "denoise": 32, "tone": 0, "crop": 0 }
            } }

# 取消任务
POST /api/tasks/{task_id}/cancel

# 获取处理结果
GET  /api/batch-process/{task_id}/results
Response: { "total": 400, "completed": 400,
            "output_files": [...], "failed": [...] }

# 预览裁切效果 (单张, 不保存)
POST /api/batch-process/preview-crop
Body: { "photo_id": 123, "crop_config": {...} }
Response: JPEG 缩略图

# 预览水印效果 (单张, 不保存)
POST /api/batch-process/preview-watermark
Body: { "photo_id": 123, "watermark_layers": [...] }
Response: JPEG 缩略图
```

### 8.2 任务执行

批处理任务在现有 `tasks` 异步任务系统中执行:
- 注册为新任务类型 `batch_process`
- 在 `tasks` 表中记录状态、进度、当前阶段
- 每张照片处理状态记录在 `batch_process_items` 新表中, 支持断点续传

### 8.3 新增数据库表

```sql
-- 注意: photos.id 为 TEXT (UUID), 此处 photo_id 必须匹配
CREATE TABLE batch_process_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,           -- 关联 tasks.id
    photo_id TEXT NOT NULL,          -- 关联 photos.id (UUID)
    phase TEXT DEFAULT 'pending',    -- pending|denoise|tone|crop|watermark|done|error
    denoise_output TEXT,             -- PureRAW 输出 DNG 路径
    tone_output TEXT,                -- LR 调色输出路径
    final_output TEXT,               -- 最终 JPG 路径
    error_msg TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photo_id) REFERENCES photos(id)
);
CREATE INDEX idx_bpi_task_id ON batch_process_items(task_id);
CREATE INDEX idx_bpi_photo_id ON batch_process_items(photo_id);

CREATE TABLE processed_photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id TEXT NOT NULL,          -- 原始 RAW 照片 ID (UUID)
    task_id TEXT NOT NULL,           -- 批处理任务 ID
    file_path TEXT NOT NULL,         -- 处理后 JPG 路径
    crop_preset TEXT,                -- 使用的裁切预设
    watermark_preset TEXT,           -- 使用的水印预设
    config_json TEXT,                -- 完整处理配置 JSON
    width INTEGER,                   -- 最终输出尺寸 (含 info-bar)
    height INTEGER,
    file_size INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photo_id) REFERENCES photos(id)
);
CREATE INDEX idx_pp_task_id ON processed_photos(task_id);
CREATE INDEX idx_pp_photo_id ON processed_photos(photo_id);
```

## 9. 前端 UI 设计 (概要)

### 9.1 批处理配置页面

新增路由 `/batch-process`, 包含以下配置区域:

```
┌─ 照片筛选 ───────────────────────────────────┐
│  最低星级: ★★☆☆ [2 ▼]                        │
│  共 1,234 张 RAW, 预计 487 张通过筛选          │
└──────────────────────────────────────────────┘

┌─ 降噪设置 ───────────────────────────────────┐
│  [✓] 启用 DxO PureRAW 降噪                    │
│  算法: [DeepPRIME XD3 ▼]                      │
│  亮度降噪: [40] ████████░░  色度降噪: [50]     │
└──────────────────────────────────────────────┘

┌─ 调色设置 ───────────────────────────────────┐
│  [✓] 启用自动调色                              │
│  工具: ○ Lightroom Classic  ○ darktable-cli   │
└──────────────────────────────────────────────┘

┌─ 裁切设置 ───────────────────────────────────┐
│  预设: [4K壁纸 ▼] [手机壁纸] [社交方图]        │
│         [鸟类特写] [电影宽幅] [原图裁切]        │
│  ─── 或自定义 ───                              │
│  宽高比: [16:9 ▼]   输出: [3840×2160       ]  │
│  构图:   ◉居中  ○三分法  ○紧凑特写  ○环境留白  │
│  ┌────────────────────┐                       │
│  │   [裁切预览缩略图]  │  ← 实时预览           │
│  └────────────────────┘                       │
└──────────────────────────────────────────────┘

┌─ 水印设置 ───────────────────────────────────┐
│  预设: [简约版权 ▼] [品牌Logo] [防盗水印]      │
│         [鸟类图鉴] [社交分享] [无水印]          │
│  ─── 或自定义 ───                              │
│  水印层:                                       │
│  ┌ [1] 文字水印 ─────────────────────────┐    │
│  │ 文字: [© Name     ]  字号: [48]        │    │
│  │ 位置: [右下▼]  透明度: [50%] ████░░░░  │    │
│  │ [✓]投影                         [删除] │    │
│  └────────────────────────────────────────┘    │
│  [+ 添加水印层]                                │
│  ┌────────────────────┐                       │
│  │   [水印预览缩略图]  │  ← 实时预览           │
│  └────────────────────┘                       │
└──────────────────────────────────────────────┘

┌─ 输出设置 ───────────────────────────────────┐
│  格式: [JPEG ▼]  质量: [95]  输出目录: [...]   │
└──────────────────────────────────────────────┘

        [ 开始处理 (预计 487 张, 约 2.5 小时) ]
```

### 9.2 任务进度页面

复用现有 DashboardView 的任务监控, 扩展显示:
- 当前处理阶段 (降噪/调色/裁切/水印)
- 每阶段进度条
- 已完成/总数
- 当前处理的文件名
- 预计剩余时间

## 10. 文件系统布局

```
data/
├── exports/
│   └── {task_id}/
│       ├── config.json              # 本次批处理配置快照
│       ├── denoise/                 # PureRAW 输出 DNG (临时)
│       │   ├── DSC09514-DxO_DeepPRIME XD3.dng
│       │   └── ...
│       ├── toned/                   # LR 调色输出 (临时)
│       │   ├── DSC09514.tiff
│       │   └── ...
│       └── final/                   # 最终输出 JPG
│           ├── DSC09514_4k_wallpaper.jpg
│           └── ...
├── watermarks/                      # 用户上传的 Logo 图片
│   └── my_logo.png
└── batch_process_config.json        # 用户上次使用的配置
```

中间文件 (denoise/, toned/) 在任务完成后可选清理。

## 11. 性能估算

以 1000 张 Sony ARW 输入, 假设 40% 通过筛选 (400 张):

| 阶段 | 单张耗时 | 数量 | 总计 | 备注 |
|------|---------|------|------|------|
| 识别+评分 | ~3s | 1000 | ~50 min | 现有管线, MPS 加速 |
| PureRAW 降噪 | ~12s | 400 | ~80 min | Apple Neural Engine |
| LR Auto Tone | ~3s | 400 | ~20 min | 需 LR 前台运行 |
| 裁切 | <0.5s | 400 | ~3 min | Pillow/PIL |
| 水印 | <0.5s | 400 | ~3 min | Pillow/PIL |
| **总计** | | | **~2.5h** | 全自动无人值守 |

磁盘空间:
- RAW 输入: ~40MB/张 × 1000 = ~40GB
- DNG 中间: ~50MB/张 × 400 = ~20GB (可清理)
- TIFF 中间: ~100MB/张 × 400 = ~40GB (可清理)
- JPG 输出: ~5MB/张 × 400 = ~2GB

## 12. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| PureRAW UI Scripting 不稳定 | 降噪环节失败 | 半自动模式回退: 脚本导入, 人工点处理 |
| LR autoTone() 需 Develop 模块 | 调色受限 | 回退到 darktable-cli |
| PureRAW 版本更新 UI 变化 | AppleScript 定位失效 | UI 元素用可配置模板 |
| YOLO 检测框不准导致裁切偏 | 鸟被部分裁切 | bird_padding ≥ 1.2 + 裁后完整性验证 |
| 处理中断 (断电/崩溃) | 任务丢失 | batch_process_items 逐张记录, 支持断点续传 |
| 中间文件占用磁盘 | 磁盘满 | 任务完成后自动清理 denoise/, toned/ |
| 裁切后分辨率太低 (鸟太小) | 画质差 | tight 模式下检查: 如果裁切区域 < 目标分辨率的 50%, 警告用户 |
| 信息条水印中文乱码 | 显示异常 | 使用 PingFang SC 字体, 遵守 UTF-8 规则 |

## 13. 依赖项

### 13.1 必须安装

| 依赖 | 用途 | 安装方式 | 现状 |
|------|------|---------|------|
| DxO PureRAW 6 | 降噪 | 已安装 | ✅ |
| Lightroom Classic | 调色 | 需用户已安装 | 需确认 |
| Pillow | 裁切/水印/输出 | pip install Pillow | 需安装 |

### 13.2 可选安装

| 依赖 | 用途 | 安装方式 |
|------|------|---------|
| darktable | 调色回退方案 | `brew install --cask darktable` |
| rawpy | RAW 预览提取 | `pip install rawpy` (已在 requirements.txt) |

### 13.3 系统权限

- 辅助功能权限: 系统偏好设置 → 隐私与安全 → 辅助功能 → 添加终端/Python
- 用于 PureRAW 和 LR 的 AppleScript UI Scripting

## 14. EXIF 元数据保留

最终输出的 JPG 应携带原始 RAW 的关键 EXIF 信息。Pillow 默认不复制 EXIF。

**处理方式**: 使用项目已有的 ExifTool 工具链, 从原始 RAW 复制 EXIF 到最终 JPG:

```python
# 复制 EXIF (排除缩略图, 保留拍摄参数/GPS/日期)
exiftool_manager.copy_metadata(
    source=original_raw_path,
    dest=final_jpg_path,
    tags=["-all:all", "-icc_profile:all", "--ThumbnailImage"]
)
```

遵守 CLAUDE.md 规则: 中文字段 (如 XMP:Title 鸟种名) 通过 UTF-8 临时文件写入。

info-bar 水印已在画面上显示 EXIF 信息, 但文件级 EXIF 仍然保留, 便于后续软件读取。

## 15. 不在范围内

- Windows 平台支持 (PureRAW/LR UI Scripting 为 macOS 专用)
- 视频处理
- 多用户并发批处理
- 云端部署
- RAW 格式间转换 (如 ARW → DNG 不经过降噪)
