"""auth / admin 路由共享的 FastAPI 依赖。

身份信息来自 ``JWTAuthMiddleware`` 注入的 ``X-User-ID`` / ``X-User-Role`` 头
（框架的 ``get_current_user_id`` 契约）；本层只做读取与角色校验。
"""

from fastapi import Depends, Header, HTTPException

from backend.auth.db import get_db  # noqa: F401  # 便于路由统一从 deps 引入


def current_user_id(
    x_user_id: str = Header(..., alias="X-User-ID"),
) -> str:
    return x_user_id


def current_user_role(
    x_user_role: str | None = Header(None, alias="X-User-Role"),
) -> str | None:
    return x_user_role


async def require_admin(
    role: str | None = Depends(current_user_role),
    user_id: str = Depends(current_user_id),
) -> str:
    """要求当前用户为 admin，否则 403；返回 user_id 供 handler 使用。"""
    if role != "admin":
        raise HTTPException(403, "需要管理员权限")
    return user_id
