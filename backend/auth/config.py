# -*- coding: utf-8 -*-
"""auth 配置集中入口。

所有依赖 backend/.env 的鉴权配置都从这里读取。本模块在导入时即
``load_dotenv``，且必须先于其它 auth 模块（routes / main）的 ``os.getenv``
被导入，否则 .env 中的配置不会生效（历史 bug：JWT_SECRET 在
``load_dotenv`` 之前被读取，导致自定义密钥被忽略）。

JWT_SECRET 为必填：缺失即抛错，拒绝启动（开发与生产同等要求）。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# backend/ 目录：config.py 位于 backend/auth/，故 parent.parent
_BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BASE_DIR / ".env")


def _parse_bool(value: str | None) -> bool | None:
    """宽松解析布尔环境变量；无法识别时返回 None（交给调用方自动判断）。"""
    if value is None:
        return None
    v = value.strip().lower()
    if v in ("true", "1", "yes", "on"):
        return True
    if v in ("false", "0", "no", "off"):
        return False
    return None


def _resolve_secret() -> str:
    secret = (os.getenv("JWT_SECRET") or "").strip()
    if not secret:
        raise RuntimeError(
            "必须设置 JWT_SECRET，拒绝启动。"
            ' 生成: python -c "import secrets;print(secrets.token_urlsafe(48))"'
        )
    return secret


JWT_SECRET: str = _resolve_secret()
JWT_ACCESS_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "120"))
JWT_REFRESH_EXPIRE_DAYS: int = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "7"))

# Cookie Secure 标志：留空=自动(跟随请求 scheme)；true/false=强制。
# 部署在 TLS 终止代理后面时，需显式设 COOKIE_SECURE=true 才能带上 Secure。
_COOKIE_SECURE = _parse_bool(os.getenv("COOKIE_SECURE"))


def resolve_cookie_secure(scheme: str) -> bool:
    """决定 auth cookie 是否带 Secure 标志。

    - ``COOKIE_SECURE`` 显式设置 → 强制按其值；
    - 未设置 → 自动：仅当请求自身为 https 时才 Secure。
    """
    if _COOKIE_SECURE is not None:
        return _COOKIE_SECURE
    return scheme == "https"
