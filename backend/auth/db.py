"""auth 专属 SQLAlchemy 引擎 / 会话工厂。

注意：auth 使用独立的 ``DeclarativeBase``（与 agentscope 存储的 ``_Base`` 区分），
但共享同一个 SQLite 文件（路径由 ``backend.settings`` 统一提供）。
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from backend.settings import get_settings


class Base(DeclarativeBase):
    pass


engine: AsyncEngine = create_async_engine(
    get_settings().db_url,
    future=True,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI 依赖：提供一个请求级数据库会话，请求结束自动关闭。"""
    async with SessionLocal() as session:
        yield session
