# backend/tests/test_middleware.py
import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from backend.auth.middleware import JWTAuthMiddleware, parse_cookies
from backend.auth.security import create_access_token, create_refresh_token

SECRET = "test-secret-0123456789abcdef0123456789ab"


def _inner_app():
    """记录下游收到的 X-User-ID / X-User-Role 头。"""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def whoami(request):
        return JSONResponse({
            "uid": request.headers.get("X-User-ID"),
            "role": request.headers.get("X-User-Role"),
        })

    async def health(request):
        return JSONResponse({"ok": True, "uid": request.headers.get("X-User-ID")})

    app = Starlette(routes=[Route("/whoami", whoami), Route("/health", health)])
    app.add_middleware(JWTAuthMiddleware, secret=SECRET)
    return app


@pytest.mark.asyncio
async def test_parse_cookies():
    c = parse_cookies("a=1; b=2; cc_access=xyz")
    assert c == {"a": "1", "b": "2", "cc_access": "xyz"}


@pytest.mark.asyncio
async def test_protected_without_cookie_401():
    async with AsyncClient(transport=ASGITransport(app=_inner_app()),
                           base_url="http://test") as ac:
        r = await ac.get("/whoami")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_valid_cookie_injects_headers_and_strips_spoof():
    tok, _ = create_access_token("alice", "admin", SECRET)
    app = _inner_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies={"cc_access": tok}) as ac:
        # 客户端伪造的 X-User-ID 必须被剥掉
        r = await ac.get("/whoami",
                         headers={"X-User-ID": "attacker", "X-User-Role": "user"})
    assert r.status_code == 200
    assert r.json() == {"uid": "alice", "role": "admin"}


@pytest.mark.asyncio
async def test_expired_token_401():
    tok, _ = create_access_token("alice", "user", SECRET, expire_minutes=-1)
    async with AsyncClient(transport=ASGITransport(app=_inner_app()),
                           base_url="http://test", cookies={"cc_access": tok}) as ac:
        r = await ac.get("/whoami")
    assert r.status_code == 401
    assert r.json()["code"] == "token_expired"


@pytest.mark.asyncio
async def test_health_gets_sentinel_without_cookie():
    async with AsyncClient(transport=ASGITransport(app=_inner_app()),
                           base_url="http://test") as ac:
        r = await ac.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "uid": "__health_check__"}


@pytest.mark.asyncio
async def test_refresh_token_rejected_as_access():
    # 拿 refresh token 当 cc_access —— type != "access" 分支，普通无效（无 code）
    tok, _ = create_refresh_token("alice", SECRET)
    async with AsyncClient(transport=ASGITransport(app=_inner_app()),
                           base_url="http://test", cookies={"cc_access": tok}) as ac:
        r = await ac.get("/whoami")
    assert r.status_code == 401
    assert "code" not in r.json()


@pytest.mark.asyncio
async def test_garbage_token_401_without_code():
    # 完全无法解码的 token —— 走 jwt.InvalidTokenError 分支，无 code 字段
    async with AsyncClient(transport=ASGITransport(app=_inner_app()),
                           base_url="http://test",
                           cookies={"cc_access": "garbage.notavalidtoken"}) as ac:
        r = await ac.get("/whoami")
    assert r.status_code == 401
    assert "code" not in r.json()


# ---------------------------------------------------------------------------
# SPA 同源托管：未登录用户必须能取到登录入口与静态资源
# ---------------------------------------------------------------------------
def _spa_inner_app():
    """模拟后端托管 frontend/dist：/、/login、/assets/* 返回 SPA；
    /whoami 代表业务 API（须鉴权）。"""
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def spa(request):
        return JSONResponse({"page": "spa",
                             "uid": request.headers.get("X-User-ID")})

    app = Starlette(routes=[
        Route("/", spa),
        Route("/login", spa),
        Route("/setup", spa),
        Route("/assets/{file:path}", spa),
        Route("/whoami", spa),
    ])
    app.add_middleware(JWTAuthMiddleware, secret=SECRET)
    return app


@pytest.mark.asyncio
async def test_spa_entry_public_without_cookie():
    async with AsyncClient(transport=ASGITransport(app=_spa_inner_app()),
                           base_url="http://test") as ac:
        for path in ("/", "/login", "/setup", "/assets/app.js", "/assets/css/x.css"):
            r = await ac.get(path)
            assert r.status_code == 200, path
            assert r.json()["page"] == "spa"


@pytest.mark.asyncio
async def test_spa_public_strips_spoofed_user_header():
    # 即使放行 SPA，客户端伪造的 X-User-ID 也必须被剥掉，不能透传给下游
    async with AsyncClient(transport=ASGITransport(app=_spa_inner_app()),
                           base_url="http://test",
                           headers={"X-User-ID": "attacker"}) as ac:
        r = await ac.get("/")
    assert r.status_code == 200
    assert r.json()["uid"] is None


@pytest.mark.asyncio
async def test_non_public_api_path_still_401_without_cookie():
    # 放行只针对 SPA 入口/静态资源；业务 API 路径未认证仍 401
    async with AsyncClient(transport=ASGITransport(app=_spa_inner_app()),
                           base_url="http://test") as ac:
        r = await ac.get("/whoami")
    assert r.status_code == 401
