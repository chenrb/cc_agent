# -*- coding: utf-8 -*-
"""CC Agent 后端服务启动入口。

完整对齐 agentscope/examples/agent_service，仅做两处替换：
  - 持久化存储：RedisStorage -> AsyncSQLAlchemyStorage（SQLite）
  - 消息总线：InMemoryMessageBus -> RedisMessageBus（始终 Redis，单/多进程通用）
"""
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware

from agentscope.app import create_app, SubAgentTemplate
from agentscope.app.hub import ClawSkillHub, GitHubMCPHub
# 注：channels（Discord/飞书）需要支持 channel 的存储后端（RedisStorage）。
# 本项目用 SQLite，故不启用 channels。Web UI 走 HTTP API 直连，无需渠道。
from agentscope.app.message_bus import RedisMessageBus
from agentscope.app.rag.knowledge_base_manager import CollectionPerKbManager
from agentscope.app.storage import AsyncSQLAlchemyStorage
from agentscope.app.workspace_manager import LocalWorkspaceManager
from agentscope.mcp import MCPClient, HttpMCPConfig, StdioMCPConfig
from agentscope.middleware import AgenticMemoryMiddleware, MiddlewareBase
from agentscope.permission import PermissionContext, PermissionMode
from agentscope.rag import QdrantStore
from agentscope.workspace import WorkspaceBase

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# --------------------------------------------------------------------------
# 默认 MCP 服务器：browser-use（需本机 npx / Node>=20）；AMAP 地图按需开启
# --------------------------------------------------------------------------
default_mcps = [
    MCPClient(
        name="browser-use",
        mcp_config=StdioMCPConfig(
            command="npx",
            args=["@playwright/mcp@latest"],
        ),
        is_stateful=True,
    ),
]

if os.getenv("AMAP_API_KEY"):
    default_mcps.append(
        MCPClient(
            name="amap",
            mcp_config=HttpMCPConfig(
                url=(
                    f"https://mcp.amap.com/mcp?key={os.environ['AMAP_API_KEY']}"
                ),
            ),
            is_stateful=False,
        ),
    )

# --------------------------------------------------------------------------
# ① 持久化存储：SQLite（create_tables=True 自动建表，dev 无需跑 Alembic）
# --------------------------------------------------------------------------
db_path = BASE_DIR / os.getenv("AGENT_DB_NAME", "cc_agent.db")
storage = AsyncSQLAlchemyStorage(
    url=f"sqlite+aiosqlite:///{db_path.as_posix()}",
    create_tables=True,
)

# --------------------------------------------------------------------------
# ② 消息总线：始终 Redis（默认 localhost:6379，可用环境变量覆盖）
# --------------------------------------------------------------------------
message_bus = RedisMessageBus(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    db=int(os.getenv("REDIS_DB", "0")),
    password=os.getenv("REDIS_PASSWORD") or None,
)

# --------------------------------------------------------------------------
# 工作区 + 知识库（内存 Qdrant 向量库，每个 KB 一个 collection）
# --------------------------------------------------------------------------
workspace_manager = LocalWorkspaceManager(
    basedir=str(BASE_DIR / "workspaces"),
    default_mcps=default_mcps,
)

vector_store = QdrantStore(location=":memory:")


# --------------------------------------------------------------------------
# 长期记忆：Markdown 文件，存于会话工作区（PER_AGENT 隔离，跨会话保留）
# --------------------------------------------------------------------------
async def longterm_memory_factory(
    user_id: str,
    agent_id: str,
    session_id: str,
    workspace: WorkspaceBase,
) -> list[MiddlewareBase]:
    """每个 chat turn 调用一次，挂载基于文件的长期记忆中间件。"""
    del user_id, agent_id, session_id
    return [
        AgenticMemoryMiddleware(
            workdir=workspace.workdir,
            backend=workspace.get_backend(),
        ),
    ]


app = create_app(
    storage=storage,
    message_bus=message_bus,
    workspace_manager=workspace_manager,
    knowledge_base_manager=CollectionPerKbManager(
        storage=storage,
        vector_store=vector_store,
    ),
    mcp_hubs=[GitHubMCPHub()],
    skill_hubs=[ClawSkillHub(api_token=os.getenv("CLAWHUB_API_TOKEN"))],
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
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        ),
    ],
    title="CC Agent",
)


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
