"""
认证 API

- POST /auth/login    — 登录，返回 JWT
- GET  /auth/me       — 当前用户信息
- POST /auth/password — 修改密码
- POST /auth/register — 管理员创建用户
- GET  /auth/users    — 管理员查看用户列表
- DELETE /auth/users/{user_id} — 管理员删除用户
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from models.database import get_db, verify_password, _hash_password

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# ── JWT 配置 ──
_JWT_SECRET = os.environ.get("JWT_SECRET", "")
if not _JWT_SECRET:
    _JWT_SECRET = secrets.token_hex(32)
    logger.warning("JWT_SECRET 未设置，使用随机密钥（重启后 token 将失效）")

JWT_EXPIRES = 7 * 24 * 3600  # 7 天

# 不需要认证的路径前缀
AUTH_EXEMPT_PATHS = {"/api/auth/login", "/api/identify"}


# ── 简易 JWT（纯标准库，无额外依赖）──

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def create_token(payload: dict) -> str:
    """签发 JWT (HS256)。"""
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64url_encode(json.dumps(payload).encode())
    sig_input = f"{header}.{body}"
    sig = hmac.new(_JWT_SECRET.encode(), sig_input.encode(), hashlib.sha256).digest()
    return f"{sig_input}.{_b64url_encode(sig)}"


def verify_token(token: str) -> dict | None:
    """验证 JWT，返回 payload 或 None。"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        sig_input = f"{parts[0]}.{parts[1]}"
        expected = hmac.new(_JWT_SECRET.encode(), sig_input.encode(), hashlib.sha256).digest()
        actual = _b64url_decode(parts[2])
        if not hmac.compare_digest(expected, actual):
            return None
        payload = json.loads(_b64url_decode(parts[1]))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


# ── 请求模型 ──

class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "user"


# ── 权限依赖 ──

def require_admin(request: Request):
    """FastAPI Depends：仅允许 admin 角色访问。"""
    user = getattr(request.state, "user", None)
    if not user or user.get("role") != "admin":
        raise HTTPException(403, "需要管理员权限")


# ── 端点 ──

@router.post("/auth/login")
async def login(req: LoginRequest, db=Depends(get_db)):
    """用户名密码登录，返回 JWT。"""
    row = db.execute(
        "SELECT id, username, password_hash, salt, role FROM users WHERE username = ?",
        (req.username,),
    ).fetchone()
    if not row or not verify_password(req.password, row["password_hash"], row["salt"]):
        raise HTTPException(401, "用户名或密码错误")

    token = create_token({
        "sub": row["id"],
        "username": row["username"],
        "role": row["role"],
        "exp": int(time.time()) + JWT_EXPIRES,
    })
    return {"token": token, "username": row["username"], "role": row["role"]}


@router.get("/auth/me")
async def me(request: Request):
    """返回当前登录用户信息。"""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "未登录")
    return {
        "username": user.get("username"),
        "user_id": user.get("sub"),
        "role": user.get("role", "user"),
    }


@router.post("/auth/password")
async def change_password(req: ChangePasswordRequest, request: Request, db=Depends(get_db)):
    """修改当前用户密码。"""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "未登录")

    row = db.execute(
        "SELECT password_hash, salt FROM users WHERE id = ?", (user["sub"],)
    ).fetchone()
    if not row or not verify_password(req.old_password, row["password_hash"], row["salt"]):
        raise HTTPException(400, "原密码错误")

    if len(req.new_password) < 4:
        raise HTTPException(400, "新密码至少 4 位")

    new_hash, new_salt = _hash_password(req.new_password)
    db.execute(
        "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
        (new_hash, new_salt, user["sub"]),
    )
    db.commit()
    return {"message": "密码修改成功"}


# ── 用户管理（仅管理员） ──

@router.post("/auth/register", dependencies=[Depends(require_admin)])
async def register(req: RegisterRequest, db=Depends(get_db)):
    """管理员创建新用户。"""
    if req.role not in ("admin", "user"):
        raise HTTPException(400, "role 必须是 admin 或 user")
    if len(req.username) < 2:
        raise HTTPException(400, "用户名至少 2 位")
    if len(req.password) < 4:
        raise HTTPException(400, "密码至少 4 位")

    existing = db.execute(
        "SELECT id FROM users WHERE username = ?", (req.username,)
    ).fetchone()
    if existing:
        raise HTTPException(409, "用户名已存在")

    password_hash, salt = _hash_password(req.password)
    user_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (id, username, password_hash, salt, role) VALUES (?, ?, ?, ?, ?)",
        (user_id, req.username, password_hash, salt, req.role),
    )
    db.commit()
    return {"id": user_id, "username": req.username, "role": req.role}


@router.get("/auth/users", dependencies=[Depends(require_admin)])
async def list_users(db=Depends(get_db)):
    """管理员查看用户列表。"""
    rows = db.execute(
        "SELECT id, username, role, created_at FROM users ORDER BY created_at"
    ).fetchall()
    return {"users": [dict(r) for r in rows]}


@router.delete("/auth/users/{user_id}", dependencies=[Depends(require_admin)])
async def delete_user(user_id: str, request: Request, db=Depends(get_db)):
    """管理员删除用户（不能删除自己）。"""
    current_user = getattr(request.state, "user", None)
    if current_user and current_user.get("sub") == user_id:
        raise HTTPException(400, "不能删除当前登录的管理员账户")

    row = db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(404, "用户不存在")

    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    return {"message": "用户已删除"}
