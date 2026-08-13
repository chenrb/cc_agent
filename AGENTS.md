# AGENTS.md

ZCode 智能体在 `cc_agent` 仓库工作时的说明文件。

## 项目简介

**CC Agent** —— 基于 [AgentScope](https://github.com/agentscope-ai/agentscope) 框架搭建的前后端分离智能体应用。仓库包含三个顶层目录：

| 目录 | 技术栈 | 角色 |
|------|--------|------|
| `agentscope/` | Python | AgentScope 框架的**内嵌可编辑副本**。通过 `[tool.uv.sources]` 以 `editable = true` 方式从 `./agentscope` 安装，是后端导入的框架源码——请视为依赖，而非应用代码。（其中体量较大的 `examples/web_ui/` 已 gitignore。） |
| `backend/` | Python 3.13、FastAPI、uv | 应用服务。对 `agentscope.app.create_app` 的薄封装。 |
| `frontend/` | React 19 + TS + Vite 8、pnpm | Web 控制台（聊天、智能体、MCP/技能市场、知识库、定时任务、渠道、凭证）。 |

根目录 `README.md` 目前内容为空——请阅读代码，不要依赖 README。

## 常用命令

### 后端（Python，由 `uv` 管理）

```bash
uv sync                         # 按 uv.lock 安装/锁定依赖（首次运行）
uv run python -m backend.main   # 启动开发服务：uvicorn 监听 0.0.0.0:8000
# reload 随平台：Linux/macOS 开启热重载；Windows 关闭（其 SelectorEventLoop
# 不支持 asyncio 子进程，而 agentscope workspace 依赖 exec_shell），需手动重启
```

- 要求 Python **>=3.13**（`.python-version` 锁定 3.13）。
- 存储为 SQLite（`backend/cc_agent.db`，通过 `create_tables=True` 自动建表）。**开发期无需运行 Alembic 迁移。**
- lint/format：`uv run ruff check backend` / `uv run ruff format backend`（配置在 `pyproject.toml [tool.ruff]`，排除 `agentscope/`）。
- 测试：`uv run pytest backend/tests`（鉴权与 admin 路由单测；框架自带的 `agentscope/tests/` 属于内嵌库，不属于本应用）。

### 前端（pnpm）

```bash
cd frontend
pnpm install
pnpm dev          # vite 开发服务器
pnpm build        # tsc -b && vite build（既是类型检查也是构建）
pnpm lint         # eslint .
pnpm lint:fix
```

`pnpm build` 是唯一的类型检查入口——没有单独的 `tsc` / `typecheck` 脚本。

## 运行时要求与配置

后端的消息总线（`RedisMessageBus`，默认 `localhost:6379`）**硬依赖 Redis**，单进程开发也需要。SQLite 为持久化层；知识库使用内存版 Qdrant 向量库。

将 `backend/.env.example` 复制为 `backend/.env` 即可覆盖默认值。所有环境变量由 `backend/settings.py`（pydantic-settings）统一加载——**优先级：环境变量 > `backend/.env` > 字段默认值**。环境变量：

- `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` / `REDIS_PASSWORD` —— 消息总线（`REDIS_DB` 为 Redis 逻辑库索引，默认 `0`）。
- `AGENT_DB_NAME` —— SQLite 文件名（相对 `backend/`，默认 `cc_agent.db`）。
- `AMAP_API_KEY` *（可选）* —— 启用高德地图 MCP 服务。
- `CLAWHUB_API_TOKEN` *（可选）* —— 技能市场鉴权。
- `JWT_SECRET` —— **必填**，缺失/为空即拒绝启动（`backend/settings.py` 的 `field_validator` 校验）；`JWT_ACCESS_EXPIRE_MINUTES`（默认 `120`）/ `JWT_REFRESH_EXPIRE_DAYS`（默认 `7`）。
- `CC_BOOTSTRAP_ADMIN_USERNAME` / `CC_BOOTSTRAP_ADMIN_PASSWORD` —— 首次启动引导的初始管理员（仅在 users 表为空时生效）。
- `CORS_ALLOWED_ORIGINS` —— 逗号分隔的来源列表，留空则不挂 CORS 中间件。
- `COOKIE_SECURE` —— 留空=自动（跟随请求 scheme）；`true`/`false`=强制。

默认装配的 MCP 服务为 `browser-use`（stdio，`npx @playwright/mcp@latest`）——宿主机需具备 **Node >=20 + npx**。

## 架构边界（改动时务必注意）

- **后端结构**：`backend/settings.py`（pydantic-settings，配置唯一来源）→ `backend/app.py`（`create_application()` 工厂，完成应用装配）→ `backend/main.py`（瘦入口，仅 `from backend.app import app` + uvicorn `__main__`）。鉴权子系统在 `backend/auth/`：`db.py`（引擎/会话/`get_db` 依赖）、`models.py`、`schemas.py`、`deps.py`（`current_user_id`/`require_admin` 等）、`routes.py`（`auth_router` 前缀 `/auth` + `admin_router` 前缀 `/admin/users`）、`security.py`、`middleware.py`（ASGI JWT 中间件）、`bootstrap.py`、`spa.py`、`config.py`（`resolve_cookie_secure` 派生逻辑）。所有 handler 经 `Depends(get_db)` 取会话。
- `backend/app.py`（原 `main.py`）相对 `agentscope/examples/agent_service` **刻意做了两处替换**：`RedisStorage → AsyncSQLAlchemyStorage`、`InMemoryMessageBus → RedisMessageBus`。不要把它"简化"回上游默认实现。
- **渠道（Discord/飞书）已启用**：agentscope 的 `AsyncSQLAlchemyStorage` 本身不实现 channel 持久化（基类默认 `NotImplementedError`）。为保持 agentscope 副本干净，channel 适配放在应用层——`backend/storage.py` 的 `CCAgentStorage(AsyncSQLAlchemyStorage)` 子类覆盖那 6 个 channel 方法，`app.py` 用它替代基类。关键约定：`ChannelRecord` 的时间戳是 ISO 字符串而非 `datetime`，故 channel 读写**绕过通用 `_write_row`/`_from_record`/`_to_record`**——`payload` 列存完整 record dump（读取的唯一真相来源），`user_id`/`channel_type`/`platform_bot_id`（全局 UNIQUE）仅作索引；`ChannelRow` 继承 agentscope 的 `_JsonRecordMixin` 以便 `create_tables=True` 自动建表。`app.py` 经 `channels=[FeishuChannel, DiscordChannel]` 注册类型。真正接通平台还需配置 bot 凭证。
- 长期记忆按 agent 隔离，以 Markdown 形式存放在会话工作区（`AgenticMemoryMiddleware`，`PER_AGENT` 隔离，跨会话保留）。
- 修改后端行为时，请查阅 `agentscope/src/agentscope/`（尤其 `app/`、`agent/`、`middleware/`、`mcp/`）——那里是 `create_app` 暴露 API 的权威实现。

## 前端约定

- **路径别名**：`@/*` → `frontend/src/*`（`tsconfig.app.json` 与 `vite.config.ts` 均已配置）。优先使用 `@/...` 导入。
- **API 客户端**（`frontend/src/api/client.ts`）：base URL 与用户 ID **未硬编码**——来自 `localStorage` 的 `server_url` 和 `username`，每次请求会带 `X-User-ID` 头。应用在 `server_url` 设置前会先进入 **Setup 页面**。错误默认通过 `sonner` toast 提示，除非传入 `silent: true`。新增接口写在 `src/api/*`，通过 `src/hooks/*` 消费。
- **导入顺序受约束**（ESLint `import-x/order`，强制执行）：builtin → external → internal → index，组间空行，字母升序。该规则**对 `src/components/ui/**` 关闭**——这些是 shadcn 生成代码（样式 `radix-nova`，基色 `neutral`，图标库 `lucide`）；请用 shadcn CLI 重新生成而非手工调整，也不要收紧它们的 lint。
- **用户可见文案必须国际化**：i18next + react-i18next，文案在 `src/i18n/locales/en.json` 与 `zh.json`（`fallbackLng: 'en'`）。新增字符串需**同时**写入两个 locale 文件。
- 样式：TailwindCSS 4 + shadcn/ui。用 `@/lib/utils` 的 `cn()` 合并类名。
- 聊天工具输出由 `src/components/chat/tool-renderers/` 下各工具对应的组件渲染；接入新工具 UI 时新增一个。
