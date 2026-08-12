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


async def _add_users(*specs):
    """直接插入额外用户。specs: (username, role, is_active) 三元组。"""
    async with SessionLocal() as s:
        for username, role, is_active in specs:
            s.add(models.User(username=username, password_hash=hash_password("pw"),
                              role=role, is_active=is_active))
        await s.commit()


async def _uid(ac, username):
    r = await ac.get("/admin/users")
    assert r.status_code == 200
    for u in r.json():
        if u["username"] == username:
            return u["id"]
    raise AssertionError(f"user {username!r} not found")


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


# --- 保护规则 ①：不能删除自己 ---
@pytest.mark.asyncio
async def test_cannot_delete_self(app_admin):
    async with AsyncClient(transport=ASGITransport(app=app_admin), base_url="http://test") as ac:
        await _login(ac)
        me = (await ac.get("/auth/me")).json()
        r = await ac.delete(f"/admin/users/{me['id']}")
    assert r.status_code == 400
    assert "删除" in r.json()["detail"]


# --- 保护规则 ②：不能禁用自己 ---
# （原 test_cannot_disable_last_admin 实际命中的是本规则：目标为 admin 自己，
#   在到达“最后 admin”判断前即被规则 ② 拦截。此处如实标注为规则 ② 覆盖。）
@pytest.mark.asyncio
async def test_cannot_disable_self(app_admin):
    async with AsyncClient(transport=ASGITransport(app=app_admin), base_url="http://test") as ac:
        await _login(ac)
        me = (await ac.get("/auth/me")).json()
        r = await ac.patch(f"/admin/users/{me['id']}", json={"is_active": False})
    assert r.status_code == 400
    assert "禁用" in r.json()["detail"]


# --- 保护规则 ③：不能降级自己的角色 ---
@pytest.mark.asyncio
async def test_cannot_demote_self(app_admin):
    async with AsyncClient(transport=ASGITransport(app=app_admin), base_url="http://test") as ac:
        await _login(ac)
        me = (await ac.get("/auth/me")).json()
        r = await ac.patch(f"/admin/users/{me['id']}", json={"role": "user"})
    assert r.status_code == 400
    assert "降级" in r.json()["detail"]


# --- 保护规则 ④（PATCH）：禁用最后一个启用 admin ---
# 实现为 count-before 语义（变更前统计 active admin，cnt<=1 即拦截）。
# admin 是当前唯一启用 admin；再 seed 一个非启用的 admin2，对其进行禁用：
# 目标非自己（规则 ② 不拦截）、不改 role（规则 ③ 不拦截），直达规则 ④，cnt==1 → 400。
@pytest.mark.asyncio
async def test_cannot_disable_last_admin(app_admin):
    await _add_users(("admin2", "admin", False))
    async with AsyncClient(transport=ASGITransport(app=app_admin), base_url="http://test") as ac:
        await _login(ac)
        uid = await _uid(ac, "admin2")
        r = await ac.patch(f"/admin/users/{uid}", json={"is_active": False})
    assert r.status_code == 400
    assert "管理员" in r.json()["detail"]


# --- 保护规则 ④（DELETE）：删除最后一个启用 admin ---
# 同上：admin 唯一启用 admin，admin2 为非启用 admin；删除 admin2 命中规则 ④，cnt==1 → 400。
@pytest.mark.asyncio
async def test_cannot_delete_last_admin(app_admin):
    await _add_users(("admin2", "admin", False))
    async with AsyncClient(transport=ASGITransport(app=app_admin), base_url="http://test") as ac:
        await _login(ac)
        uid = await _uid(ac, "admin2")
        r = await ac.delete(f"/admin/users/{uid}")
    assert r.status_code == 400
    assert "管理员" in r.json()["detail"]


# --- 正面对照：存在 >=2 个启用 admin 时，操作另一个 admin 应成功 ---
@pytest.mark.asyncio
async def test_can_manage_other_admin_when_multiple_active(app_admin):
    # seed 后共 3 个启用 admin：admin、admin2、admin3
    await _add_users(("admin2", "admin", True), ("admin3", "admin", True))
    async with AsyncClient(transport=ASGITransport(app=app_admin), base_url="http://test") as ac:
        await _login(ac)
        uid2 = await _uid(ac, "admin2")
        uid3 = await _uid(ac, "admin3")
        # 禁用 admin2：变更前 cnt==3 → 放行 → 200（仍剩 admin、admin3 两个启用 admin）
        r1 = await ac.patch(f"/admin/users/{uid2}", json={"is_active": False})
        assert r1.status_code == 200
        # 删除 admin3：变更前 cnt==2 → 放行 → 204（仍剩 admin 一个启用 admin）
        r2 = await ac.delete(f"/admin/users/{uid3}")
        assert r2.status_code == 204
