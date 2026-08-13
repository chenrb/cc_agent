# backend/tests/test_db.py
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import DeclarativeBase

from backend.auth.db import Base, SessionLocal, engine


def test_db_module_exports():
    assert isinstance(engine, AsyncEngine)
    assert issubclass(Base, DeclarativeBase)
    assert SessionLocal is not None


@pytest.mark.asyncio
async def test_engine_connects_and_create_all_runs():
    # models 尚未定义（Task 3），create_all 在空 metadata 上应为 no-op 且不报错
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
