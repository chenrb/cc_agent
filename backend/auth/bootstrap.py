# backend/auth/bootstrap.py
from sqlalchemy import func, select
from backend.auth.db import SessionLocal
from backend.auth import models
from backend.auth.security import hash_password


async def bootstrap_admin(username: str | None, password: str | None) -> None:
    async with SessionLocal() as s:
        count = (await s.execute(select(func.count()).select_from(models.User))).scalar_one()
        if count > 0:
            return  # 已有用户，跳过
    if not username or not password:
        raise RuntimeError(
            "users 表为空且未设置 CC_BOOTSTRAP_ADMIN_USERNAME/PASSWORD，无法引导首个管理员")
    async with SessionLocal() as s:
        s.add(models.User(username=username,
                          password_hash=hash_password(password), role="admin"))
        await s.commit()
