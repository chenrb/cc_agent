# backend/tests/test_bootstrap.py
import pytest
from backend.auth.db import engine, Base, SessionLocal
from backend.auth import models  # noqa
from backend.auth.bootstrap import bootstrap_admin


async def _reset():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_creates_admin_when_empty():
    await _reset()
    await bootstrap_admin("admin", "pw")
    async with SessionLocal() as s:
        from sqlalchemy import select
        u = (await s.execute(select(models.User))).scalar_one()
    assert u.username == "admin" and u.role == "admin"


@pytest.mark.asyncio
async def test_skips_when_nonempty():
    await _reset()
    await bootstrap_admin("admin", "pw")
    # 第二次：不应重复创建或报错
    await bootstrap_admin("other", "xx")
    async with SessionLocal() as s:
        from sqlalchemy import select
        n = len((await s.execute(select(models.User))).scalars().all())
    assert n == 1


@pytest.mark.asyncio
async def test_raises_when_empty_and_no_creds():
    await _reset()
    with pytest.raises(RuntimeError):
        await bootstrap_admin(None, None)
    with pytest.raises(RuntimeError):
        await bootstrap_admin("admin", None)
