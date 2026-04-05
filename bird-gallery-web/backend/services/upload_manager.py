"""
分块上传管理服务

管理大文件的分块上传会话：初始化、接收块、状态查询、合并校验。
"""

import os
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


def init_session(db, upload_id: str, filename: str, file_size: int,
                 chunk_size: int, file_type: str) -> dict:
    """初始化上传会话。"""
    chunk_count = (file_size + chunk_size - 1) // chunk_size
    db.execute(
        """INSERT INTO upload_sessions
           (id, filename, file_size, chunk_count, chunk_size, file_type, uploaded_chunks, status)
           VALUES (?, ?, ?, ?, ?, ?, '[]', 'uploading')""",
        (upload_id, filename, file_size, chunk_count, chunk_size, file_type),
    )
    db.commit()
    return {
        "upload_id": upload_id,
        "chunk_count": chunk_count,
        "chunk_size": chunk_size,
    }


def record_chunk(db, upload_id: str, index: int) -> list[int]:
    """记录已上传的分块，返回当前已上传列表。"""
    row = db.execute(
        "SELECT uploaded_chunks FROM upload_sessions WHERE id = ?",
        (upload_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"Upload session {upload_id} not found")

    chunks = json.loads(row["uploaded_chunks"] or "[]")
    if index not in chunks:
        chunks.append(index)
        chunks.sort()
    db.execute(
        "UPDATE upload_sessions SET uploaded_chunks = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (json.dumps(chunks), upload_id),
    )
    db.commit()
    return chunks


def get_session_status(db, upload_id: str) -> dict | None:
    """查询上传会话状态。"""
    row = db.execute(
        "SELECT * FROM upload_sessions WHERE id = ?",
        (upload_id,),
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["uploaded_chunks"] = json.loads(result["uploaded_chunks"] or "[]")
    return result


def merge_chunks(chunks_dir: str, output_path: str, chunk_count: int,
                 expected_hash: str | None = None) -> str:
    """合并所有分块为完整文件并校验 SHA256。

    Returns:
        实际文件的 SHA256 哈希值
    """
    h = hashlib.sha256()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'wb') as out:
        for i in range(chunk_count):
            chunk_path = os.path.join(chunks_dir, str(i))
            if not os.path.exists(chunk_path):
                raise FileNotFoundError(f"Chunk {i} missing")
            with open(chunk_path, 'rb') as chunk_f:
                while True:
                    data = chunk_f.read(8192)
                    if not data:
                        break
                    out.write(data)
                    h.update(data)

    actual_hash = h.hexdigest()
    if expected_hash and actual_hash != expected_hash:
        os.unlink(output_path)
        raise ValueError(f"Hash mismatch: expected {expected_hash}, got {actual_hash}")

    return actual_hash
