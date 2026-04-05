"""
视频处理服务

- FFmpeg 转码（H.264 MP4）
- 帧提取（四档采样策略）
- 帧分析结果聚合
"""

import os
import subprocess
import json
import logging
import re

logger = logging.getLogger(__name__)


def get_video_info(video_path: str) -> dict | None:
    """用 ffprobe 获取视频元信息。"""
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, start_new_session=True)
        if result.returncode != 0:
            return None
        info = json.loads(result.stdout)

        video_stream = None
        for s in info.get("streams", []):
            if s.get("codec_type") == "video":
                video_stream = s
                break

        if not video_stream:
            return None

        # 解析帧率
        fps_str = video_stream.get("r_frame_rate", "30/1")
        parts = fps_str.split("/")
        fps = float(parts[0]) / float(parts[1]) if len(parts) == 2 and float(parts[1]) != 0 else 30.0

        duration = float(info.get("format", {}).get("duration", 0))
        frame_count = int(video_stream.get("nb_frames", 0))
        if frame_count == 0 and duration > 0:
            frame_count = int(duration * fps)

        return {
            "duration": duration,
            "fps": round(fps, 2),
            "frame_count": frame_count,
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
            "codec": video_stream.get("codec_name", "unknown"),
        }
    except Exception as e:
        logger.error("ffprobe failed for %s: %s", video_path, e)
        return None


def transcode_video(input_path: str, output_path: str, progress_callback=None) -> bool:
    """转码为 H.264 MP4，返回是否成功。

    - 超过 1080p 的视频自动缩放到 1080p
    - macOS 优先使用 VideoToolbox 硬件加速
    - 限制 CPU 线程数，避免占满所有核心
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 检查源视频分辨率
    info = get_video_info(input_path)
    height = info.get("height", 0) if info else 0
    duration = info.get("duration", 0) if info else 0

    # 超过 1080p 则缩放；scale filter: 保持宽高比，高度对齐到偶数
    vf_filters = []
    if height > 1080:
        vf_filters.append("scale=-2:1080")

    # 尝试 VideoToolbox 硬件加速（macOS），失败则回退软编码
    success = False
    for use_hw in (True, False):
        cmd = ["ffmpeg", "-y", "-threads", "4"]

        if use_hw:
            # VideoToolbox 硬件解码 + 编码
            cmd += ["-hwaccel", "videotoolbox", "-i", input_path]
            if vf_filters:
                cmd += ["-vf", ",".join(vf_filters)]
            cmd += ["-c:v", "h264_videotoolbox", "-b:v", "8M"]
        else:
            cmd += ["-i", input_path]
            if vf_filters:
                cmd += ["-vf", ",".join(vf_filters)]
            cmd += ["-c:v", "libx264", "-crf", "23", "-preset", "fast"]

        cmd += [
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            output_path,
        ]

        # 超时：按视频时长 × 10 计算，4K 转码需要更多时间，最少 120s
        timeout = max(120, int(duration * 10)) if duration > 0 else 3600

        try:
            logger.info("Transcode %s (hw=%s, scale=%s, timeout=%ds)",
                        os.path.basename(input_path), use_hw,
                        "1080p" if height > 1080 else "original", timeout)
            result = subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                timeout=timeout, start_new_session=True,
            )
            if result.returncode == 0:
                success = True
                break
            if use_hw:
                logger.warning("VideoToolbox failed, falling back to software: %s",
                               result.stderr[-500:] if result.stderr else "")
                continue
            logger.error("Software transcode failed: %s",
                         result.stderr[-500:] if result.stderr else "")
        except subprocess.TimeoutExpired:
            logger.error("Transcode timed out after %ds (hw=%s)", timeout, use_hw)
            # 清理不完整的输出文件
            if os.path.exists(output_path):
                os.remove(output_path)
            if use_hw:
                continue
        except Exception as e:
            logger.error("Transcode failed: %s", e)
            if use_hw:
                continue

    if progress_callback:
        progress_callback(100)
    return success


def extract_frames(
    video_path: str,
    output_dir: str,
    strategy: str = "interval",
    interval: int = 10,
) -> list[dict]:
    """提取视频帧。

    strategy: 'keyframe' | 'interval' | 'scene' | 'all'
    interval: 用于 interval 策略，每 N 帧取一帧

    返回 [{frame_number, timestamp, path}, ...]
    """
    os.makedirs(output_dir, exist_ok=True)

    info = get_video_info(video_path)
    if not info:
        return []

    fps = info["fps"]

    if strategy == "keyframe":
        # 仅关键帧
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", "select='eq(pict_type\\,I)'",
            "-vsync", "vfr",
            os.path.join(output_dir, "frame_%06d.jpg"),
        ]
    elif strategy == "all":
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            os.path.join(output_dir, "frame_%06d.jpg"),
        ]
    elif strategy == "interval":
        # 每 interval 帧取一帧
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"select='not(mod(n\\,{interval}))'",
            "-vsync", "vfr",
            os.path.join(output_dir, "frame_%06d.jpg"),
        ]
    else:
        # scene change
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", "select='gt(scene\\,0.3)'",
            "-vsync", "vfr",
            os.path.join(output_dir, "frame_%06d.jpg"),
        ]

    try:
        subprocess.run(cmd, capture_output=True, timeout=600, start_new_session=True)
    except Exception as e:
        logger.error("Frame extraction failed: %s", e)
        return []

    # 收集提取的帧
    frames = []
    frame_files = sorted(f for f in os.listdir(output_dir) if f.startswith("frame_") and f.endswith(".jpg"))

    for idx, fname in enumerate(frame_files):
        if strategy == "interval":
            frame_num = idx * interval
        else:
            frame_num = idx

        timestamp = frame_num / fps if fps > 0 else 0
        frames.append({
            "frame_number": frame_num,
            "timestamp": round(timestamp, 3),
            "path": os.path.join(output_dir, fname),
        })

    return frames


def generate_thumbnail(video_path: str, output_path: str, seek_sec: float = 1.0) -> bool:
    """用 FFmpeg 从视频提取一帧作为缩略图。"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 获取视频时长，确保 seek 不超出范围
    info = get_video_info(video_path)
    duration = info.get("duration", 0) if info else 0
    seek = min(seek_sec, max(duration * 0.1, 0.1)) if duration > 0 else 0

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(seek),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        "-vf", "scale='min(640,iw)':-2",
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30, start_new_session=True)
        return result.returncode == 0
    except Exception as e:
        logger.error("Thumbnail generation failed for %s: %s", video_path, e)
        return False


def synthesize_burst_video(
    image_paths: list[str],
    output_path: str,
    framerate: int = 20,
    resolution: str = "1920x1080",
) -> bool:
    """将连拍照片序列合成为 H.264 MP4。"""
    import tempfile

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 使用 concat demuxer file list
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        for img_path in image_paths:
            f.write(f"file '{img_path}'\n")
            f.write(f"duration {1.0 / framerate}\n")
        # 最后一帧也需要 duration
        if image_paths:
            f.write(f"file '{image_paths[-1]}'\n")
        list_path = f.name

    w, h = resolution.split("x")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", list_path,
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=300, start_new_session=True)
        return result.returncode == 0
    except Exception as e:
        logger.error("Burst synthesis failed: %s", e)
        return False
    finally:
        os.unlink(list_path)
