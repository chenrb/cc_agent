"""集中配置入口（pydantic-settings）。

所有运行时配置的唯一来源：环境变量优先，其次 ``backend/.env``，最后字段默认值。
取代原先散落在 ``main.py`` / ``auth/config.py`` / ``auth/db.py`` 的 ``os.getenv``。

``JWT_SECRET`` 必填：缺失或为空时 ValidationError 拒绝启动（开发与生产同等要求）。
"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录（settings.py 位于 backend/）
BASE_DIR: Path = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- JWT 鉴权 ----
    jwt_secret: str
    jwt_access_expire_minutes: int = 120
    jwt_refresh_expire_days: int = 7

    # ---- 首管引导（env 为 CC_ 前缀，故显式 alias）----
    bootstrap_admin_username: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CC_BOOTSTRAP_ADMIN_USERNAME"),
    )
    bootstrap_admin_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CC_BOOTSTRAP_ADMIN_PASSWORD"),
    )

    # ---- Cookie Secure：None=自动(跟随请求 scheme)；True/False=强制 ----
    cookie_secure: bool | None = None

    # ---- SQLite 持久化 ----
    agent_db_name: str = "cc_agent.db"

    # ---- Redis 消息总线 ----
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    # ---- 可选功能 ----
    amap_api_key: str | None = None
    clawhub_api_token: str | None = None

    # ---- CORS（逗号分隔来源，留空则不启用）----
    cors_allowed_origins: str = ""

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_non_empty(cls, v: str) -> str:
        secret = v.strip()
        if not secret:
            raise ValueError(
                "必须设置 JWT_SECRET，拒绝启动。"
                ' 生成: python -c "import secrets;print(secrets.token_urlsafe(48))"'
            )
        return secret

    @property
    def db_path(self) -> Path:
        """SQLite 数据库绝对路径（位于 backend/ 下）。"""
        return BASE_DIR / self.agent_db_name

    @property
    def db_url(self) -> str:
        """SQLAlchemy async SQLite URL。"""
        return f"sqlite+aiosqlite:///{self.db_path.as_posix()}"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """返回全局 Settings 单例（首次调用时读取环境/.env 并校验）。"""
    return Settings()
