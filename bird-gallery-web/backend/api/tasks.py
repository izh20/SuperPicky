"""异步任务查询 API"""

from fastapi import APIRouter, Depends, HTTPException
from models.database import get_db
from models.schemas import TaskResponse

router = APIRouter(tags=["tasks"])


@router.get("/tasks/latest/{task_type}", response_model=TaskResponse)
async def get_latest_task_by_type(task_type: str, db=Depends(get_db)):
    """获取某类型最新的任务。"""
    row = db.execute(
        "SELECT * FROM tasks WHERE type = ? ORDER BY created_at DESC LIMIT 1",
        (task_type,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "No tasks found")
    return TaskResponse(**dict(row))


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db=Depends(get_db)):
    """查询异步任务状态与进度。"""
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Task not found")
    return TaskResponse(**dict(row))


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, db=Depends(get_db)):
    """取消一个 pending 或 running 的任务。"""
    row = db.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Task not found")
    if row["status"] not in ("pending", "running"):
        return {"message": "Task already finished"}
    db.execute(
        "UPDATE tasks SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (task_id,),
    )
    db.commit()
    return {"message": "Task cancelled"}
