# backend/auth/middleware.py
import json

import jwt

from backend.auth.security import decode_token

PUBLIC_PATHS = {("POST", "/auth/login"), ("POST", "/auth/refresh")}
_HEALTH_PATH = ("GET", "/health")
_HEALTH_SENTINEL = "__health_check__"

# SPA 同源托管（后端托管 frontend/dist）下，未登录用户也必须能取到登录入口
# 与静态资源，否则登录页本身会被中间件挡成 401。这里只放行登录流程必需的
# 入口和纯静态资源——它们不含任何业务数据；真正的鉴权仍在 API 路由层。
# 注意：前端业务路由（/chat、/mcp 等）与 agentscope API 前缀重名，未登录直接
# 访问会命中 API 而非 SPA，属既有托管限制，不在本放行规则处理范围。
_SPA_PUBLIC_EXACT = {
    ("GET", "/"),  # SPA 入口 index.html
    ("GET", "/login"),  # 登录页
    ("GET", "/setup"),  # 首次后端地址配置（登录前）
    ("GET", "/favicon.ico"),
}
_SPA_PUBLIC_PREFIXES = ("/assets/",)  # vite 构建产物（js/css/图片）


def _is_public_spa(method: str, path: str) -> bool:
    if (method, path) in _SPA_PUBLIC_EXACT:
        return True
    return method == "GET" and any(path.startswith(p) for p in _SPA_PUBLIC_PREFIXES)


def parse_cookies(cookie_header: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in cookie_header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _get_cookie(scope, name):
    for key, value in scope.get("headers", []):
        if key == b"cookie":
            return parse_cookies(value.decode("latin-1")).get(name)
    return None


def _strip_user_headers(scope):
    scope["headers"] = [
        (k, v) for k, v in scope["headers"] if k.lower() not in (b"x-user-id", b"x-user-role")
    ]


def _inject_user(scope, user_id, role):
    _strip_user_headers(scope)
    scope["headers"].append((b"x-user-id", user_id.encode("latin-1")))
    if role is not None:
        scope["headers"].append((b"x-user-role", role.encode("latin-1")))


async def _send_json(send, status, detail, code=None):
    body = {"detail": detail}
    if code:
        body["code"] = code
    raw = json.dumps(body).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(raw)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": raw})


class JWTAuthMiddleware:
    def __init__(self, app, secret, access_cookie="cc_access"):
        self.app = app
        self.secret = secret
        self.access_cookie = access_cookie

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        method, path = scope["method"], scope["path"]

        if (method, path) in PUBLIC_PATHS:
            _strip_user_headers(scope)
            return await self.app(scope, receive, send)

        if _is_public_spa(method, path):
            _strip_user_headers(scope)
            return await self.app(scope, receive, send)

        if (method, path) == _HEALTH_PATH:
            _inject_user(scope, _HEALTH_SENTINEL, None)
            return await self.app(scope, receive, send)

        token = _get_cookie(scope, self.access_cookie)
        if not token:
            return await _send_json(send, 401, "未认证")

        try:
            payload = decode_token(token, self.secret)
        except jwt.ExpiredSignatureError:
            return await _send_json(send, 401, "token 已过期", code="token_expired")
        except jwt.InvalidTokenError:
            return await _send_json(send, 401, "无效 token")

        if payload.get("type") != "access":
            return await _send_json(send, 401, "无效 token")

        user_id = payload.get("sub")
        if user_id is None:
            return await _send_json(send, 401, "无效 token")
        _inject_user(scope, user_id, payload.get("role"))
        return await self.app(scope, receive, send)
