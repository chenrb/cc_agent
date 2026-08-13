"""auth 派生配置。

原始环境配置（JWT_SECRET、超时、cookie_secure 等）已统一迁入
``backend.settings``。本模块仅保留与 cookie Secure 标志相关的派生逻辑——
它在请求期被反复调用，且取值需跟随 ``COOKIE_SECURE`` 配置。
"""

from backend.settings import get_settings


def resolve_cookie_secure(scheme: str) -> bool:
    """决定 auth cookie 是否带 Secure 标志。

    - ``COOKIE_SECURE`` 显式设置 → 强制按其值；
    - 未设置 → 自动：仅当请求自身为 https 时才 Secure。

    部署在 TLS 终止代理后面时，需显式设 ``COOKIE_SECURE=true`` 才能带上 Secure。
    """
    cookie_secure = get_settings().cookie_secure
    if cookie_secure is not None:
        return cookie_secure
    return scheme == "https"
