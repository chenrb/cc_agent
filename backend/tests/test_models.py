# backend/tests/test_models.py
import pytest
from sqlalchemy import inspect
from backend.auth.db import engine, Base
from backend.auth import models  # noqa: F401


def _columns(meta, table):
    return {c["name"] for c in inspect(meta).get_columns(table)}


@pytest.mark.asyncio
async def test_users_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    def _u(sync_conn):
        return _columns(sync_conn, "users")
    async with engine.connect() as conn:
        cols = await conn.run_sync(_u)
    assert {"id", "username", "password_hash", "role", "is_active",
            "created_at", "updated_at"} <= cols
