# CC Agent JWT 鉴权登录系统设计

- 日期：2026-08-12
- 状态：待复核
- 作者：chenrb（经 brainstorming 协作产出）

## 1. 背景与目标

### 1.1 现状
CC Agent 后端目前**没有任何身份认证**。agentscope 框架（内嵌依赖，不可改动）的身份来源是单一依赖函数 `get_current_user_id`（`agentscope/src/agentscope/app/deps.py:32`），它读取 HTTP 头 `X-User-ID` 并原样返回，不解析、不签名、不查表——`user_id` 完全是客户端自报、服务端无条件信任。所有 agentscope 路由的数据隔离都建立在这个不可信的 `user_id` 上。详见前置探索结论。

### 1.2 目标
- 账号密码登录，用户数据入库；JWT 作 token。
- Access token 有效期 2 小时；refresh token 7 天。
- 前端登录页。
- **硬约束：不改动 agentscope 源码**（它作为 Python 依赖引入），所有改动在 `backend/`（及 `frontend/`）完成。

### 1.3 非目标（V1 不做）
自助注册、邮箱找回密码、双因素(2FA)、自助改密页、"记住我"勾选（refresh 7d 已覆盖）、注册页。

## 2. 概念澄清：Cookie 与 JWT 正交

| 概念 | 含义 | 本设计 |
|---|---|---|
| **JWT** | token 的**格式/内容**（HS256 签名 JSON：`sub`/`role`/`jti`/`type`/`exp`/`iat`） | **不变**，仍是 JWT |
| **Cookie** | token 的**运输方式** | 由 `localStorage + Authorization 头` 改为 `httpOnly cookie` |

JWT 放进 httpOnly cookie，是「JWT-in-cookie」：JS 读不到 token（防 XSS 窃取），但 token 本身仍是 JWT。中间件照常 `jwt.decode(cookie 的值)`。

## 3. 关键设计决策（brainstorming 结论）

1. **账号模型**：多用户，管理员后台开通。首个管理员由环境变量在启动时引导创建；管理员可在页面里增删/启用禁用账号；不开放公开注册。需要 admin 角色 + 用户管理页。
2. **Token 策略**：access token 2h + refresh token 7d。refresh token 落库（可撤销 + 轮换）。
3. **撤销时机**：延迟撤销。中间件**无状态**（只验 JWT 签名+过期，不查库）。管理员禁用用户后，login/refresh 被 `is_active` 拦住，已发出的 access token 最多再活 2h。
4. **首管引导**：环境变量（`CC_BOOTSTRAP_ADMIN_USERNAME/PASSWORD`）在 users 表为空时自动创建首个管理员；表非空跳过。
5. **token 运输**：httpOnly cookie（`cc_access`/`cc_refresh`），**同源/同站部署**。
6. **注入机制（方案 A）**：纯 ASGI 中间件做「默认拒绝」网关，把 cookie 里的 JWT 解出 `user_id`/`role`，剥掉客户端自带的 `X-User-ID`/`X-User-Role` 后注入从 JWT 解出的值，下游 agentscope 无感知。
7. **V1 一并实现后端托管前端**：backend 用 `StaticFiles` 挂 `frontend/dist` + SPA fallback，生产开箱同源。
8. **/health 公开 + 哨兵用户**：中间件对 `GET /health` 注入保留哨兵 `X-User-ID: __health_check__`（只满足 agentscope 对该头的强制要求；该用户不拥有任何数据、无任何权限）。

## 4. 架构总览

```
浏览器 ──(httpOnly cookie: cc_access/cc_refresh; credentials:'include')──▶ 后端(FastAPI)
                                                                          │
                            ┌─────────────────────────────────────────────┤
                            │ 1. CORS 中间件(最外, 仅 dev 跨源时生效)       │
                            │ 2. JWTAuthMiddleware(ASGI):                 │
                            │    - 公开白名单(login/refresh/health) 放行   │
                            │    - 读 cc_access cookie → jwt.decode        │
                            │    - 剥客户端 X-User-ID/Role, 注入 JWT 解出值│
                            │ 3. agentscope 路由(原样, 读 X-User-ID)        │
                            │    + /auth/* 路由(本项目)                     │
                            │    + /admin/users 路由(本项目, 需 admin)      │
                            │    + StaticFiles 托管前端(SPA fallback)       │
                            └─────────────────────────────────────────────┘
```

**数据流（登录）**：
`POST /auth/login`(公开) → 校验密码 + `is_active` → 签 access(2h)+refresh(7d)，refresh `jti` 落库 → `Set-Cookie: cc_access; cc_refresh`(HttpOnly, Lax) → 响应体 `{user:{username,role}, expires_in}`。

**数据流（鉴权请求）**：浏览器带 cookie → 中间件验 `cc_access` → 注入 `X-User-ID`/`X-User-Role` → agentscope 路由正常服务。

**数据流（刷新）**：access 过期 → 中间件 401(expired) → 前端调 `POST /auth/refresh`(读 `cc_refresh` cookie) → 轮换（旧 refresh 撤销、签新、新 jti 落库）→ 重设 cookie → 前端重试原请求。

## 5. 后端设计

### 5.1 新增模块结构（全在 `backend/auth/`，不动 agentscope）

```
backend/auth/
├── __init__.py
├── db.py          # 自有 async SQLAlchemy 引擎/会话（复用 cc_agent.db，独立 metadata）
├── models.py      # User、RefreshToken
├── security.py    # argon2 密码哈希 + JWT 编解码 + cookie 工具
├── middleware.py  # JWTAuthMiddleware(纯 ASGI)
├── bootstrap.py   # 启动引导首个管理员
└── routes.py      # APIRouter: /auth/* + /admin/users/*
```

`backend/main.py` 中 `app = create_app(...)` 之后：建表 → 引导首管 → `app.include_router(auth_router)` → 中间件经 `extra_middlewares` 注入 → 挂 StaticFiles 托管前端。

### 5.2 数据模型

复用同一个 `cc_agent.db`（`AGENT_DB_NAME`），独立 `MetaData`，`create_all` 只建本项目两张表，不动 agentscope 表。

**`users`**

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | |
| `username` | str, unique, indexed | JWT 的 `sub`；也是下发的 `X-User-ID`（保证与现有自报 username 数据连续） |
| `password_hash` | str | argon2 哈希 |
| `role` | str | `admin` / `user`，默认 `user` |
| `is_active` | bool | 默认 true（管理员可禁用） |
| `created_at` / `updated_at` | datetime | |

**`refresh_tokens`**（服务端可撤销 + 轮换）

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | int PK | |
| `jti` | str, unique, indexed | refresh token 的 JWT id |
| `user_id` | int FK→users.id | |
| `expires_at` | datetime | |
| `revoked` | bool | 默认 false |
| `created_at` | datetime | |

### 5.3 密码与 JWT

- 密码哈希：argon2-cffi（`PasswordHasher`）。
- JWT：PyJWT，HS256，密钥来自 `JWT_SECRET`。
- Access token claims：`{sub:username, role, jti, type:"access", iat, exp(now+JWT_ACCESS_EXPIRE_MINUTES)}`。
- Refresh token claims：`{sub:username, jti, type:"refresh", iat, exp(now+JWT_REFRESH_EXPIRE_DAYS*1440)}`。
- 依赖加入 `pyproject.toml`：`pyjwt`、`argon2-cffi`。

### 5.4 ASGI 中间件（`middleware.py`，核心）

**为什么纯 ASGI 而非 `BaseHTTPMiddleware`**：后者把下游包成新 `Request`，对 `scope["headers"]` 的改写不会传到 agentscope 路由读到的 `Header`。纯 ASGI 直接改 `scope["headers"]`（`(bytes,bytes)` 列表）才可靠。

逻辑：

```
请求进来(scope.type != "http" → 直接放行，如 websocket)
├─ method == OPTIONS → 放行（dev 跨源 preflight，由外层 CORS 兜底；保留哨兵防御）
├─ 命中"公开白名单"(method+path 精确) →
│   ├─ GET /health → 注入哨兵 x-user-id=__health_check__（无权限），放行
│   └─ POST /auth/login | POST /auth/refresh → 原样放行
├─ 否则取 cookie 头，解析 cc_access
│   ├─ 缺失 → 401 {"detail":"未认证"}
│   ├─ jwt.decode 失败(签名错/过期) → 401（过期用专用 detail 提示前端去刷新）
│   └─ claims.type != "access" → 401
├─ 校验通过：sub(username)、role
├─ 改写 scope["headers"]：
│   ① 删客户端自带 x-user-id / x-user-role（堵伪造）
│   ② 追加 x-user-id=<username>、x-user-role=<role>
└─ 交给下游
```

401 由中间件按 ASGI 协议直接回送（`http.response.start` + body），不经上层。

### 5.5 公开白名单（method+path 精确）

- `POST /auth/login`、`POST /auth/refresh`（无需 cookie）。
- `GET /health`（注入哨兵用户 `__health_check__`，无权限）。
- 其余（含 `POST /auth/logout`、`GET /auth/me`、全部 `/admin/users/*`、所有 agentscope 路由）**必须**带有效 `cc_access`。

### 5.6 接口

| 方法 路径 | 入参 | 返回 | 鉴权 |
|---|---|---|---|
| `POST /auth/login` | `{username, password}` | `{user:{username,role}, expires_in}` + Set-Cookie | 公开 |
| `POST /auth/refresh` | （无 body，读 cookie） | `{expires_in}` + Set-Cookie(轮换) | 公开（读 `cc_refresh`） |
| `POST /auth/logout` | （无 body） | 204 + 清 cookie | 需 access |
| `GET /auth/me` | — | `{id, username, role, is_active}` | 需 access |
| `GET /admin/users` | — | 用户列表 | 需 admin |
| `POST /admin/users` | `{username, password, role}` | 新用户 | 需 admin |
| `PATCH /admin/users/{id}` | `{is_active?, role?, password?}` | 更新 | 需 admin |
| `DELETE /admin/users/{id}` | — | 删除 | 需 admin |

- **admin 判定**：`/admin/*` 路由用 `require_admin` 依赖读中间件注入的 `X-User-Role` 头（信任边界在中间件：客户端自带头已被剥）。
- **保护规则**：禁止 admin 删除自己、禁用自己、降自己角色；禁止删除/禁用最后一个 admin（前后端都校验，后端为准）。
- **is_active 校验点**：login、refresh 两处查 `is_active`（发新 token 的入口）。被禁用用户拿不到新 token，已发出的 access ≤2h 自然失效（延迟撤销）。
- **refresh 轮换**：`/auth/refresh` 校验 refresh JWT 签名+类型+过期 → 查库 `jti` 未撤销 → 旧 `jti` 标记 `revoked`、签新 access+refresh、新 `jti` 落库 → 重设两个 cookie。
- **logout**：撤销当前 `cc_refresh` 的 `jti`（读 cookie 解出）；清两个 cookie（`Max-Age=0`）。access 因无状态最多再活 2h。

### 5.7 Cookie 属性

| Cookie | Max-Age | 属性 |
|---|---|---|
| `cc_access` | 7200（2h） | `HttpOnly; SameSite=Lax; Path=/; Secure?` |
| `cc_refresh` | 604800（7d） | `HttpOnly; SameSite=Lax; Path=/; Secure?` |

`Secure` 跟随 `request.url.scheme == "https"`，可由 env `COOKIE_SECURE` 覆盖（dev plain HTTP 下必须为 False，否则浏览器拒收）。

### 5.8 CORS（cookie 不兼容 `allow_origins=["*"]`）

- 删除现有 `allow_origins=["*"]`。
- 新增 env `CORS_ALLOWED_ORIGINS`（逗号分隔，**默认空 = 同源、不挂 CORS**）。
- 非空时才挂 `CORSMiddleware(allow_credentials=True, allow_origins=<列表>, allow_methods=["*"], allow_headers=["*"])`。
- dev：`CORS_ALLOWED_ORIGINS=http://localhost:5173`。

### 5.9 中间件顺序（关键）

CORS 必须最外层（否则中间件返回的 401 跨域时带不上 `Access-Control-*` 头）。两者都经 `create_app(..., extra_middlewares=[JWT, CORS])` 传入，**JWT 在前、CORS 在后**；`create_app` 内部顺序 `add_middleware`，后加者更靠外 → 最终 `CORS( JWT( 路由 ) )`。

### 5.10 启动装配（`backend/main.py`）

为避开与 agentscope lifespan 冲突，一次性初始化用 `asyncio.run()` 在 `create_app` 之前同步执行：

```python
asyncio.run(init_db_and_bootstrap())   # create_all(users/refresh_tokens) + 引导首管

app = create_app(
    storage=storage, message_bus=message_bus, ...,
    extra_middlewares=[
        Middleware(JWTAuthMiddleware, secret=JWT_SECRET, allowlist=PUBLIC_PATHS),
        *cors_middleware(),   # 空列表(同源) 或 [Middleware(CORSMiddleware, ...)]
    ],
    title="CC Agent",
)
app.include_router(auth_router)
mount_spa(app)   # StaticFiles 挂 frontend/dist + SPA fallback（V1）
```

**`init_db_and_bootstrap()`**：`create_all` → 查 users 是否为空：
- 空 且 `CC_BOOTSTRAP_ADMIN_*` 已设 → 插入 admin；
- 空 且未设 → **启动报错**（鉴权系统无用户无法运行）；
- 非空 → 跳过。

**`mount_spa(app)`**：`app.mount("/", StaticFiles(directory="frontend/dist", html=True))`，并对非 API/非已匹配路由回退 `index.html`（SPA history routing）。生产部署前需 `pnpm build` 产出 `frontend/dist`。

### 5.11 环境变量（追加到 `backend/.env.example`）

| 变量 | 默认 | 说明 |
|---|---|---|
| `JWT_SECRET` | —（必填） | HS256 密钥；缺失启动报错。生成：`python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `JWT_ACCESS_EXPIRE_MINUTES` | `120` | access 有效期 |
| `JWT_REFRESH_EXPIRE_DAYS` | `7` | refresh 有效期 |
| `CC_BOOTSTRAP_ADMIN_USERNAME` | `admin` | users 表空时建首管 |
| `CC_BOOTSTRAP_ADMIN_PASSWORD` | — | 同上（设了用户名就必须设密码，否则启动报错） |
| `CORS_ALLOWED_ORIGINS` | （空） | dev 填 `http://localhost:5173` |
| `COOKIE_SECURE` | 自动 | 覆盖 cookie 的 Secure 标志 |

## 6. 前端设计

### 6.1 启动流程（按顺序）

1. **定 API 基址**：客户端 base = `localStorage.server_url ?? ''`（`''`=相对=同源）。
   - 若 `server_url` 未存 → 进 **Setup 页**：只填"后端地址"（默认 `''`，dev/远程可填 `http://localhost:8000`），探测 `GET /health`（公开+哨兵）确认是 agentscope 后端，存 `server_url`。同源生产可填 `''` 直接通过。去掉 username 字段。
2. **判定登录态**：App 挂载即调 `GET /auth/me`（`credentials:'include'`）。
   - `200` → 设 user context（username/role），进入 App。
   - `401` → 跳 `/login`。
3. localStorage 仅缓存 username/role 作 UI 提示（**非权威**，服务端以 cookie 为准）。

### 6.2 `api/client.ts` 改造

- 所有请求加 `credentials: 'include'`；不发 `Authorization`、不存 token、不发 `X-User-ID`。
- **401 自动刷新重试**（前端最复杂的点）：
  ```
  请求返回 401：
  ├─ 若是 /auth/login 或 /auth/refresh 本身 → 不重试，直接抛
  ├─ 否则（共享 refreshPromise 做"单飞"）调 POST /auth/refresh(credentials:include)
  │   ├─ 成功（cookie 已轮换）→ 重试原请求一次（标记已重试防死循环）
  │   └─ 失败 → 清 UI 缓存 → 跳 /login
  ```
  并发多个 401 只发一次 `/auth/refresh`，其余等同一 Promise。

### 6.3 新增/改动文件

```
src/api/auth.ts                    # 新增：authApi(login/refresh/logout/me) + 管理员用户 CRUD
src/api/client.ts                  # 改：credentials:include；401 自动刷新重试
src/api/types.ts                   # 新增 LoginResponse、User 等
src/pages/login/index.tsx          # 新增：登录页（username + password）
src/pages/users/index.tsx          # 新增：管理员用户管理页
src/components/RequireAuth.tsx     # 新增：登录态守卫（基于 /auth/me）
src/components/RequireAdmin.tsx    # 新增：admin 守卫
src/App.tsx                        # 改：守卫 + /login + /users；挂载后 /auth/me 取 role
src/components/layout/AppSidebar.tsx # 改：admin 可见"用户管理"入口 + 登出按钮
src/i18n/locales/{en,zh}.json      # 新增登录/管理/错误文案（两份都写）
```

### 6.4 登录页（`/login`）
用户名 + 密码 + 登录按钮 + 错误提示（用现有 `Alert`/`Field`/`Input`）。提交 → `authApi.login` →（token 在 cookie，JS 不碰）→ 存 username/role 作 UI 提示 → 跳来源页或 `/chat`。

### 6.5 管理员用户管理页（`/users`，仅 admin）
表格：username / role / 状态 / 创建时间；操作：新建（对话框 username/password/role）、启用/禁用、改角色、重置密码、删除（禁删自己/最后 admin）。全部走 `credentials:'include'`。

### 6.6 路由守卫
- `<RequireAuth>`：`/auth/me` 401 → `<Navigate to="/login" state={{from}} />`。
- `<RequireAdmin>`：role≠admin → 回 `/chat`。

### 6.7 登出
侧栏"登出"按钮 → `authApi.logout()` → 后端清 cookie；前端清 UI 缓存 → `/login`。

## 7. 开发模式跨域处理

dev 下 vite(`:5173`) 与后端(`:8000`) 是**同站不同源**：
- **CORS**（看源）：不同源 → `CORS_ALLOWED_ORIGINS=http://localhost:5173` + `allow_credentials=True`。
- **SameSite**（看站点）：都是 localhost 同站 → `SameSite=Lax` cookie 会被带上，**不需要** `SameSite=None;Secure`，**不需要 HTTPS**。
- 结论：dev = `CORS_ALLOWED_ORIGINS=http://localhost:5173` + `SameSite=Lax` + `credentials:'include'`，plain HTTP 即可。

## 8. 部署（同源，V1 含后端托管前端）

- 生产：`pnpm build` 产出 `frontend/dist` → backend `mount_spa(app)` 以 `StaticFiles` + SPA fallback 托管 → SPA 与 API 同源。
- 同源时 CORS 可不挂（`CORS_ALLOWED_ORIGINS` 留空），cookie 同源自动携带。
- 远程/独立部署：通过反向代理实现同源；或按需配 `CORS_ALLOWED_ORIGINS` + 生产 HTTPS。

## 9. 安全考量与已知取舍

- **延迟撤销**：禁用用户后已签发的 access 最多再活 2h（无状态中间件，不查库）。可接受。
- **CSRF**：`SameSite=Lax` 已防御跨站 POST；状态变更接口均 POST/PATCH/DELETE 且 JSON 请求会触发 preflight。V1 不引入单独 CSRF token。
- **XSS 偷 token**：httpOnly cookie 使 JS 读不到 token，堵死此路。
- **localStorage 仅存 UI 提示**（username/role），被篡改只影响显示，不影响鉴权（服务端以 cookie 为准）。
- **哨兵 `/health` 用户** `__health_check__` 不拥有任何数据、无权限。
- **公开注册关闭**：账号只能由管理员创建。

## 10. V1 范围

**包含**：login/refresh(轮换)/logout/`/auth/me`、管理员用户 CRUD、纯 ASGI 鉴权中间件（cookie 版）、users/refresh_tokens 两表、首管 env 引导、后端托管前端(StaticFiles+SPA fallback)、登录页、管理页、路由守卫、401 自动刷新重试、Setup 简化、i18n 双语、CORS 改造、`.env.example` 更新。

**不含**：自助注册/找回密码/2FA/自助改密页/「记住我」勾选。

## 11. 文件清单

后端：`backend/auth/{__init__,db,models,security,middleware,bootstrap,routes}.py`、`backend/main.py`(改)、`backend/.env.example`(改)、`pyproject.toml`(加依赖)。
前端：见 6.3。

## 12. 未来工作

- 自助改密页、密码强度策略、登录限流/锁定（防爆破）。
- 公网部署强化：IP 白名单、反向代理 TLS、独立 liveness 探针（免 cookie）。
- access token 即时撤销（若需）：引入 jti 黑名单 + 中间件查库/缓存。
- 升级为 httpOnly + `__Host-` 前缀 cookie（同源时更严格）。
