"""应用装配工厂。

对 ``agentscope.app.create_app`` 的封装，完成 CC Agent 的两处刻意替换：
  - 持久化存储：``RedisStorage`` -> ``AsyncSQLAlchemyStorage``（SQLite）
  - 消息总线：``InMemoryMessageBus`` -> ``RedisMessageBus``（始终 Redis，单/多进程通用）

并叠加本应用自有的鉴权（JWT cookie + ASGI 中间件）、CORS、SPA 托管与 auth 初始化。
不要把这两处替换"简化"回上游默认实现（见 AGENTS.md）。
"""

from contextlib import asynccontextmanager

from agentscope.app import SubAgentTemplate, create_app
from agentscope.app.channel import DiscordChannel, FeishuChannel
from agentscope.app.hub import ClawSkillHub, GitHubMCPHub
from agentscope.app.message_bus import RedisMessageBus
from agentscope.app.rag.knowledge_base_manager import CollectionPerKbManager
from agentscope.app.workspace_manager import LocalWorkspaceManager
from agentscope.mcp import HttpMCPConfig, MCPClient, StdioMCPConfig
from agentscope.middleware import AgenticMemoryMiddleware, MiddlewareBase
from agentscope.permission import PermissionContext, PermissionMode
from agentscope.rag import QdrantStore
from agentscope.workspace import WorkspaceBase
from fastapi import FastAPI
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware

from backend.auth import models  # noqa: F401  # 注册 ORM 表到 Base.metadata
from backend.auth.bootstrap import bootstrap_admin
from backend.auth.db import Base, engine
from backend.auth.middleware import JWTAuthMiddleware
from backend.auth.routes import admin_router, auth_router
from backend.auth.spa import mount_spa
from backend.llm.glm import ZhipuCredential
from backend.settings import Settings, get_settings
from backend.storage import CCAgentStorage


def _build_default_mcps(settings: Settings) -> list[MCPClient]:
    """默认 MCP 服务器：browser-use（需本机 npx / Node>=20）；AMAP 地图按需开启。"""
    mcps = [
        MCPClient(
            name="browser-use",
            mcp_config=StdioMCPConfig(
                command="npx",
                args=["@playwright/mcp@latest"],
            ),
            is_stateful=True,
        ),
    ]
    if settings.amap_api_key:
        mcps.append(
            MCPClient(
                name="amap",
                mcp_config=HttpMCPConfig(
                    url=f"https://mcp.amap.com/mcp?key={settings.amap_api_key}",
                ),
                is_stateful=False,
            ),
        )
    return mcps


def _build_cors_middleware(settings: Settings) -> list[Middleware]:
    """CORS 中间件：仅在配置 CORS_ALLOWED_ORIGINS 时挂载。"""
    origins = settings.cors_origins
    if not origins:
        return []
    return [
        Middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]


async def longterm_memory_factory(
    user_id: str,
    agent_id: str,
    session_id: str,
    workspace: WorkspaceBase,
) -> list[MiddlewareBase]:
    """每个 chat turn 调用一次，挂载基于文件的长期记忆中间件。

    长期记忆按 agent 隔离，以 Markdown 形式存于会话工作区（PER_AGENT，跨会话保留）。
    """
    del user_id, agent_id, session_id
    return [
        AgenticMemoryMiddleware(
            workdir=workspace.workdir,
            backend=workspace.get_backend(),
        ),
    ]


async def init_db_and_bootstrap(settings: Settings) -> None:
    """建 auth 两表 + 首管引导（读 env）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await bootstrap_admin(
        settings.bootstrap_admin_username,
        settings.bootstrap_admin_password,
    )


def create_application() -> FastAPI:
    """装配并返回 FastAPI 应用。"""
    settings = get_settings()
    base_dir = settings.db_path.parent  # backend/

    # ① 持久化存储：SQLite（create_tables=True 自动建表，dev 无需跑 Alembic）
    storage = CCAgentStorage(
        url=settings.db_url,
        create_tables=True,
    )

    # ② 消息总线：始终 Redis（默认 localhost:6379，可用环境变量覆盖）
    message_bus = RedisMessageBus(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        password=settings.redis_password,
    )

    # 工作区 + 知识库（内存 Qdrant 向量库，每个 KB 一个 collection）
    workspace_manager = LocalWorkspaceManager(
        basedir=str(base_dir / "workspaces"),
        default_mcps=_build_default_mcps(settings),
    )
    vector_store = QdrantStore(location=":memory:")

    # 渠道（Discord/飞书）：SQL 后端已实现 channel 持久化（见 storage.py），
    # RedisMessageBus 提供 dispatcher/gateway 所需的 pubsub/锁/队列，故可启用。
    # 真正接通平台还需配置 bot 凭证。
    app = create_app(
        storage=storage,
        message_bus=message_bus,
        workspace_manager=workspace_manager,
        knowledge_base_manager=CollectionPerKbManager(
            storage=storage,
            vector_store=vector_store,
        ),
        mcp_hubs=[GitHubMCPHub()],
        skill_hubs=[ClawSkillHub(api_token=settings.clawhub_api_token)],
        channels=[FeishuChannel, DiscordChannel],
        extra_credentials=[ZhipuCredential],
        custom_subagent_templates=[
            SubAgentTemplate(
                type="explorer",
                description=(
                    "Read-only agents specialized in exploration tasks. It can "
                    "read files but cannot modify, create, or delete them. Use "
                    "this agent type when you need to investigate the codebase, "
                    "understand its structure, or gather information from files "
                    "to support planning—without making any changes."
                ),
                system_prompt_template=(
                    "You are {member_name}, an explorer agent in team "
                    "'{team_name}' led by {leader_name}.\n\n"
                    "Team purpose: {team_description}\n\n"
                    "Your role: {member_description}\n\n"
                    "## Responsibilities\n"
                    "- Complete the exploration tasks assigned by the team "
                    "leader.\n"
                    "- You are read-only: you may inspect files and the "
                    "codebase, but you must never modify, create, or delete "
                    "anything.\n\n"
                    "## Reporting\n"
                    "- Always report the task result back to {leader_name} using "
                    "the TeamSay tool, whether the task succeeds or fails.\n"
                    "- Keep your private reasoning private; only share "
                    "conclusions and findings that the leader needs.\n\n"
                    "Note: `TeamSay` is your ONLY channel to communicate with "
                    "{leader_name} and the other team members. Any other output "
                    "you produce is invisible to them, so anything you want them "
                    "to see MUST be sent through `TeamSay`."
                ),
                permission_context=PermissionContext(
                    mode=PermissionMode.EXPLORE,
                ),
            ),
        ],
        extra_agent_middlewares=longterm_memory_factory,
        extra_middlewares=[
            Middleware(JWTAuthMiddleware, secret=settings.jwt_secret),
            *_build_cors_middleware(settings),
        ],
        title="CC Agent",
    )

    # auth 初始化（建表 + 首管引导）挂到 app lifespan 启动阶段，先于 agentscope
    # 服务就绪。不能用模块顶层 asyncio.run()：uvicorn --reload 子进程导入模块时
    # 已处于事件循环中，asyncio.run() 会抛 "cannot be called from a running
    # event loop"。
    agentscope_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def _lifespan(application: FastAPI):
        await init_db_and_bootstrap(settings)
        async with agentscope_lifespan(application):
            yield

    app.router.lifespan_context = _lifespan

    app.include_router(auth_router)
    app.include_router(admin_router)
    mount_spa(app)
    return app


# 模块级 app 供 uvicorn 直接引用（backend.main:app / backend.app:app 均可）
app = create_application()
