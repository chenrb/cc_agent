# backend/tests/test_auth_routes.py
import os
import pytest
from datetime import timedelta
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from backend.auth.db import engine, Base, SessionLocal
from backend.auth import models  # noqa
from backend.auth.middleware import JWTAuthMiddleware
from backend.auth.routes import auth_router, set_auth_cookies  # 仅作导入存在性
from backend.auth.security import hash_password, decode_token
from backend.auth import routes as routes_mod

SECRET = "test-secret-0123456789abcdef0123456789ab"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(routes_mod, "JWT_SECRET", SECRET)
    monkeypatch.setattr(routes_mod, "ACCESS_MIN", 120)
    monkeypatch.setattr(routes_mod, "REFRESH_DAYS", 7)


@pytest.fixture
async def app_with_admin():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        s.add(models.User(username="admin", password_hash=hash_password("pw"),
                          role="admin", is_active=True))
        await s.commit()
    app = FastAPI()
    app.include_router(auth_router)
    app.add_middleware(JWTAuthMiddleware, secret=SECRET)
    return app


@pytest.mark.asyncio
async def test_login_success_sets_cookies(app_with_admin):
    async with AsyncClient(transport=ASGITransport(app=app_with_admin),
                           base_url="http://test") as ac:
        r = await ac.post("/auth/login", json={"username": "admin", "password": "pw"})
    assert r.status_code == 200
    assert r.json() == {"user": {"username": "admin", "role": "admin"},
                        "expires_in": 7200}
    cookies = {c.name for c in ac.cookies.jar}
    assert "cc_access" in cookies and "cc_refresh" in cookies


@pytest.mark.asyncio
async def test_login_wrong_password_401(app_with_admin):
    async with AsyncClient(transport=ASGITransport(app=app_with_admin),
                           base_url="http://test") as ac:
        r = await ac.post("/auth/login", json={"username": "admin", "password": "x"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_cookie(app_with_admin):
    async with AsyncClient(transport=ASGITransport(app=app_with_admin),
                           base_url="http://test") as ac:
        assert (await ac.get("/auth/me")).status_code == 401
        # 登录后
        await ac.post("/auth/login", json={"username": "admin", "password": "pw"})
        r = await ac.get("/auth/me")
        assert r.status_code == 200
        assert r.json()["username"] == "admin"


@pytest.mark.asyncio
async def test_refresh_rotates_and_old_invalid(app_with_admin):
    async with AsyncClient(transport=ASGITransport(app=app_with_admin),
                           base_url="http://test") as ac:
        await ac.post("/auth/login", json={"username": "admin", "password": "pw"})
        old_refresh = ac.cookies.get("cc_refresh")
        r1 = await ac.post("/auth/refresh")
        assert r1.status_code == 200
        new_refresh = ac.cookies.get("cc_refresh")
    assert new_refresh != old_refresh  # 轮换
    # 旧 refresh 已撤销：用旧 cookie 再刷应失败（手动塞回旧 cookie）
    async with AsyncClient(transport=ASGITransport(app=app_with_admin),
                           base_url="http://test") as ac2:
        ac2.cookies.set("cc_refresh", old_refresh, domain="test")
        r2 = await ac2.post("/auth/refresh")
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_disabled_user_cannot_login(app_with_admin):
    async with SessionLocal() as s:
        u = (await s.execute(models.User.__table__.select()
             .where(models.User.__table__.c.username == "admin"))).one()
        await s.execute(models.User.__table__.update()
            .where(models.User.__table__.c.id == u.id).values(is_active=False))
        await s.commit()
    async with AsyncClient(transport=ASGITransport(app=app_with_admin),
                           base_url="http://test") as ac:
        r = await ac.post("/auth/login", json={"username": "admin", "password": "pw"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_refresh_and_clears_cookies(app_with_admin):
    async with AsyncClient(transport=ASGITransport(app=app_with_admin),
                           base_url="http://test") as ac:
        await ac.post("/auth/login", json={"username": "admin", "password": "pw"})
        old_refresh = ac.cookies.get("cc_refresh")
        r = await ac.post("/auth/logout")
        assert r.status_code == 204
        # 响应删除两个 cookie
        names = {sc.split("=", 1)[0].strip()
                 for sc in r.headers.get_list("set-cookie")}
        assert "cc_access" in names and "cc_refresh" in names
    # 旧 refresh 已撤销：无法再刷新
    async with AsyncClient(transport=ASGITransport(app=app_with_admin),
                           base_url="http://test") as ac2:
        ac2.cookies.set("cc_refresh", old_refresh, domain="test")
        r2 = await ac2.post("/auth/refresh")
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_login_cookie_secure_forced(app_with_admin, monkeypatch):
    # TLS 终止代理场景：scheme=http，但 COOKIE_SECURE=true 应强制带 Secure
    monkeypatch.setattr(routes_mod, "resolve_cookie_secure", lambda scheme: True)
    async with AsyncClient(transport=ASGITransport(app=app_with_admin),
                           base_url="http://test") as ac:
        r = await ac.post("/auth/login", json={"username": "admin", "password": "pw"})
    assert r.status_code == 200
    set_cookie = r.headers.get_list("set-cookie")
    assert any("Secure" in sc for sc in set_cookie)


@pytest.mark.asyncio
async def test_login_cookie_secure_auto_http(app_with_admin, monkeypatch):
    # 自动模式 + http 请求 → 不带 Secure
    monkeypatch.setattr(routes_mod, "resolve_cookie_secure",
                        lambda scheme: scheme == "https")
    async with AsyncClient(transport=ASGITransport(app=app_with_admin),
                           base_url="http://test") as ac:
        r = await ac.post("/auth/login", json={"username": "admin", "password": "pw"})
    assert r.status_code == 200
    set_cookie = r.headers.get_list("set-cookie")
    assert not any("Secure" in sc for sc in set_cookie)
