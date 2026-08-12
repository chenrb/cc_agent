# backend/auth/db.py
import os
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

_DB_PATH = Path(__file__).resolve().parent.parent / os.getenv("AGENT_DB_NAME", "cc_agent.db")


class Base(DeclarativeBase):
    pass


engine: AsyncEngine = create_async_engine(
    f"sqlite+aiosqlite:///{_DB_PATH.as_posix()}",
    future=True,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
