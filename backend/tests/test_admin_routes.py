# backend/tests/test_admin_routes.py
import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from backend.auth.db import engine, Base, SessionLocal
from backend.auth import models  # noqa
from backend.auth.middleware import JWTAuthMiddleware
from backend.auth.routes import auth_router
from backend.auth.security import hash_password
from backend.auth import routes as routes_mod

SECRET = "test-secret-0123456789abcdef0123456789ab"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(routes_mod, "JWT_SECRET", SECRET)


async def _seed(app):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        s.add(models.User(username="admin", password_hash=hash_password("pw"), role="admin"))
        s.add(models.User(username="bob", password_hash=hash_password("pw"), role="user"))
        await s.commit()


@pytest.fixture
async def app_admin():
    async def _lifespan(_): yield
    app = FastAPI()
    app.include_router(auth_router)
    app.add_middleware(JWTAuthMiddleware, secret=SECRET)
    await _seed(app)
    return app


async def _login(ac):
    await ac.post("/auth/login", json={"username": "admin", "password": "pw"})


@pytest.mark.asyncio
async def test_admin_lists_users(app_admin):
    async with AsyncClient(transport=ASGITransport(app=app_admin), base_url="http://test") as ac:
        await _login(ac)
        r = await ac.get("/admin/users")
    assert r.status_code == 200
    names = {u["username"] for u in r.json()}
    assert names == {"admin", "bob"}


@pytest.mark.asyncio
async def test_non_admin_forbidden(app_admin):
    async with AsyncClient(transport=ASGITransport(app=app_admin), base_url="http://test") as ac:
        await ac.post("/auth/login", json={"username": "bob", "password": "pw"})
        r = await ac.get("/admin/users")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_disable_delete(app_admin):
    async with AsyncClient(transport=ASGITransport(app=app_admin), base_url="http://test") as ac:
        await _login(ac)
        r = await ac.post("/admin/users", json={"username": "carol",
                                                "password": "pw", "role": "user"})
        assert r.status_code == 201
        cid = r.json()["id"]
        # 禁用
        assert (await ac.patch(f"/admin/users/{cid}", json={"is_active": False})).status_code == 200
        # 删除
        assert (await ac.delete(f"/admin/users/{cid}")).status_code == 204


@pytest.mark.asyncio
async def test_cannot_delete_self(app_admin):
    async with AsyncClient(transport=ASGITransport(app=app_admin), base_url="http://test") as ac:
        await _login(ac)
        me = (await ac.get("/auth/me")).json()
        r = await ac.delete(f"/admin/users/{me['id']}")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cannot_disable_last_admin(app_admin):
    async with AsyncClient(transport=ASGITransport(app=app_admin), base_url="http://test") as ac:
        await _login(ac)
        me = (await ac.get("/auth/me")).json()
        r = await ac.patch(f"/admin/users/{me['id']}", json={"is_active": False})
    assert r.status_code == 400
