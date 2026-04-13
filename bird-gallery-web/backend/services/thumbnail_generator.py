"""
多级缩略图生成服务

级别：sm(200px) / md(800px) / lg(2000px)
存储到 data/thumbnails/{photo_id}/
支持 JPEG 和 RAW（从内嵌 JPEG 提取）。
"""

import os
import logging
from PIL import Image, ExifTags

logger = logging.getLogger(__name__)


def _get_exiftool_cmd() -> str:
    """获取项目自带的 exiftool 路径。"""
    # 项目根目录：backend/../..
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    bundled = os.path.join(project_root, 'exiftools_mac', 'exiftool')
    if os.path.exists(bundled):
        return bundled
    # 回退到系统 exiftool
    return 'exiftool'


_EXIFTOOL = _get_exiftool_cmd()

_THUMB_SIZES = {
    "sm": 200,
    "md": 800,
    "lg": 2000,
}

from app_config_pkg import config as app_config

# RAW 扩展名（需要特殊处理）
_RAW_EXTENSIONS = {'.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf', '.orf', '.rw2'}


def get_thumbnail_dir(photo_id: str) -> str:
    return app_config.thumbnails_dir(photo_id)


def get_thumbnail_path(photo_id: str, size: str) -> str | None:
    """返回缩略图路径（如果存在）。"""
    path = os.path.join(app_config.thumbnails_dir(photo_id), f"{size}.jpg")
    return path if os.path.exists(path) else None


def _fix_orientation(img: Image.Image) -> Image.Image:
    """根据 EXIF Orientation 旋转图片。"""
    try:
        exif = img.getexif()
        orientation_key = None
        for k, v in ExifTags.TAGS.items():
            if v == 'Orientation':
                orientation_key = k
                break
        if orientation_key and orientation_key in exif:
            orientation = exif[orientation_key]
            if orientation == 3:
                img = img.rotate(180, expand=True)
            elif orientation == 6:
                img = img.rotate(270, expand=True)
            elif orientation == 8:
                img = img.rotate(90, expand=True)
    except Exception:
        pass
    return img


def _open_image(file_path: str) -> Image.Image | None:
    """打开图片，对 RAW 格式尝试从内嵌 JPEG 提取。"""
    ext = os.path.splitext(file_path)[1].lower()

    if ext in _RAW_EXTENSIONS:
        # 尝试用 rawpy 提取内嵌 JPEG
        try:
            import rawpy
            with rawpy.imread(file_path) as raw:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    from io import BytesIO
                    return Image.open(BytesIO(thumb.data))
                elif thumb.format == rawpy.ThumbFormat.BITMAP:
                    return Image.fromarray(thumb.data)
        except Exception as e:
            logger.warning("RAW thumb extraction failed for %s: %s", file_path, e)
            # 回退：rawpy 全尺寸解码
            try:
                import rawpy
                with rawpy.imread(file_path) as raw:
                    rgb = raw.postprocess(half_size=True, use_camera_wb=True)
                    return Image.fromarray(rgb)
            except Exception:
                pass

        # 最终回退：用 exiftool 提取内嵌 JPEG 预览
        img = _extract_preview_via_exiftool(file_path)
        if img:
            return img

        return None
    else:
        try:
            img = Image.open(file_path)
            img.load()
            return img
        except Exception as e:
            logger.warning("Cannot open image %s: %s", file_path, e)
            return None


def _extract_preview_via_exiftool(file_path: str) -> Image.Image | None:
    """用 exiftool 从 RAW 文件提取嵌入的 JPEG 预览。"""
    import subprocess
    from io import BytesIO

    for tag in ("-JpgFromRaw", "-PreviewImage"):
        try:
            result = subprocess.run(
                [_EXIFTOOL, tag, "-b", file_path],
                capture_output=True, timeout=30,
            )
            if result.returncode == 0 and len(result.stdout) > 1000:
                img = Image.open(BytesIO(result.stdout))
                img.load()
                logger.info("Extracted preview via exiftool %s for %s (%dx%d)", tag, file_path, img.width, img.height)
                return img
        except Exception as e:
            logger.warning("exiftool %s extraction failed for %s: %s", tag, file_path, e)

    return None


def generate_thumbnail(file_path: str, photo_id: str, size: str) -> str | None:
    """生成单个尺寸的缩略图，返回保存路径。"""
    if size not in _THUMB_SIZES:
        return None

    out_path = os.path.join(get_thumbnail_dir(photo_id), f"{size}.jpg")
    if os.path.exists(out_path):
        return out_path

    img = _open_image(file_path)
    if img is None:
        return None

    img = _fix_orientation(img)

    # 转换色彩空间
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    max_dim = _THUMB_SIZES[size]
    img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    img.save(out_path, "JPEG", quality=85)
    logger.info("Generated thumbnail %s for %s (%dx%d)", size, photo_id, img.width, img.height)
    return out_path


def generate_all_thumbnails(file_path: str, photo_id: str) -> dict[str, str | None]:
    """生成所有尺寸的缩略图。"""
    results = {}
    for size in _THUMB_SIZES:
        results[size] = generate_thumbnail(file_path, photo_id, size)
    return results


def generate_preview_jpeg(file_path: str, photo_id: str) -> str | None:
    """从 RAW 文件提取全分辨率内嵌 JPEG 缓存，供 AI 推理使用。
    
    非 RAW 文件返回 None（直接用原图即可）。
    已存在时直接返回路径。
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in _RAW_EXTENSIONS:
        return None

    preview_path = os.path.join(get_thumbnail_dir(photo_id), "preview.jpg")
    if os.path.exists(preview_path):
        return preview_path

    img = _open_image(file_path)
    if img is None:
        return None

    img = _fix_orientation(img)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # 保留完整分辨率，质量 95
    img.save(preview_path, "JPEG", quality=95)
    logger.info("Generated preview JPEG for %s (%dx%d)", photo_id, img.width, img.height)
    return preview_path


def get_image_dimensions(file_path: str) -> tuple[int, int] | None:
    """获取图片宽高，支持 RAW 格式。"""
    ext = os.path.splitext(file_path)[1].lower()

    # 普通图片用 PIL
    if ext not in _RAW_EXTENSIONS:
        try:
            with Image.open(file_path) as img:
                return img.size  # (width, height)
        except Exception:
            return None

    # RAW：先用 exiftool 读取尺寸（最快最可靠）
    try:
        import subprocess
        result = subprocess.run(
            [_EXIFTOOL, "-s3", "-ExifImageWidth", "-ExifImageHeight", file_path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2:
                w, h = int(lines[0]), int(lines[1])
                if w > 0 and h > 0:
                    return (w, h)
    except Exception:
        pass

    # 回退：rawpy
    try:
        import rawpy
        with rawpy.imread(file_path) as raw:
            return (raw.sizes.width, raw.sizes.height)
    except Exception:
        pass

    # 最终回退：从嵌入预览获取纵横比
    img = _extract_preview_via_exiftool(file_path)
    if img:
        return img.size

    return None
