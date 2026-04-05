"""异步任务查询 API"""

from fastapi import APIRouter, Depends, HTTPException
from models.database import get_db
from models.schemas import TaskResponse

router = APIRouter(tags=["tasks"])


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db=Depends(get_db)):
    """查询异步任务状态与进度。"""
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Task not found")
    return TaskResponse(**dict(row))
