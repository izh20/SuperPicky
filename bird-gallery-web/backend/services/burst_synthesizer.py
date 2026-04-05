"""
连拍视频合成服务

将一组连拍照片合成为 H.264 MP4 视频。
实际合成逻辑委托给 video_processor.synthesize_burst_video()。
"""

import os
import logging

from services.video_processor import synthesize_burst_video

logger = logging.getLogger(__name__)


def synthesize_burst(db, group_id: str, output_dir: str,
                     framerate: int = 20, resolution: str = "1920x1080") -> str | None:
    """合成连拍组视频。

    Args:
        db: SQLite 连接
        group_id: 连拍组 ID
        output_dir: 输出目录
        framerate: 帧率
        resolution: 分辨率 (WxH)

    Returns:
        成功时返回输出视频路径，失败返回 None
    """
    photos = db.execute("""
        SELECT p.original_path
        FROM burst_group_photos bgp
        JOIN photos p ON p.id = bgp.photo_id
        WHERE bgp.group_id = ?
        ORDER BY bgp.position
    """, (group_id,)).fetchall()

    image_paths = [r["original_path"] for r in photos if os.path.exists(r["original_path"])]
    if not image_paths:
        logger.error("No valid images found for burst group %s", group_id)
        return None

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"burst_{group_id}.mp4")

    success = synthesize_burst_video(image_paths, output_path, framerate, resolution)
    if not success:
        logger.error("FFmpeg synthesis failed for burst group %s", group_id)
        return None

    # 更新数据库
    db.execute("UPDATE burst_groups SET video_path = ? WHERE id = ?", (output_path, group_id))
    db.commit()

    return output_path
