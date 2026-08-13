# CC Agent

基于 [AgentScope](https://github.com/agentscope-ai/agentscope) 框架构建的前后端分离智能体应用。后端用 FastAPI 包装 AgentScope 的 `create_app`，前端是一套 React + TypeScript + Vite 的聊天式控制台，支持多智能体、MCP 工具、技能市场、知识库、定时任务、渠道接入与凭证管理。

## 技术栈

| 部分 | 技术 |
|------|------|
| 后端 | Python 3.13 · FastAPI · uvicorn · SQLAlchemy + SQLite · Redis · Qdrant（内存） |
| 前端 | React 19 · TypeScript · Vite 8 · TailwindCSS 4 · shadcn/ui · i18next · React Router 7 |
| 框架 | AgentScope（本地 `./agentscope` 以 `editable` 方式安装） |
| 包管理 | uv（后端）· pnpm（前端） |

## 架构概览

```
cc_agent/
├── agentscope/        # 内嵌的 AgentScope 框架源码（editable 安装，作为依赖，非应用代码）
├── backend/           # FastAPI 应用，薄封装 agentscope.app.create_app
│   ├── main.py        # 服务入口（存储 / 消息总线 / 工作区 / 知识库 / MCP 装配）
│   ├── .env.example   # 配置模板
│   └── workspaces/    # 运行时生成（已 gitignore）
├── frontend/          # React SPA 控制台
│   └── src/
│       ├── api/       # 后端接口封装（统一 client）
│       ├── hooks/     # 数据获取 hooks
│       ├── components/# UI 组件（chat 渲染器、面板、对话框、shadcn ui 等）
│       ├── pages/     # 路由页面（chat / schedule / channel / mcp / skill / knowledge ...）
│       └── i18n/      # en.json / zh.json 多语言文案
├── pyproject.toml     # uv 项目配置，agentscope 指向 ./agentscope
└── uv.lock
```

`backend/main.py` 在 AgentScope 官方示例 `agentscope/examples/agent_service` 的基础上做了两处替换：

- **持久化存储**：`RedisStorage` → `AsyncSQLAlchemyStorage`（SQLite，`create_tables=True`，开发期无需跑 Alembic）
- **消息总线**：`InMemoryMessageBus` → `RedisMessageBus`（单/多进程统一走 Redis）

> **渠道（Discord / 飞书）已启用**：agentscope 上游的 `AsyncSQLAlchemyStorage` 默认不实现 channel 持久化（基类那 6 个方法会抛 `NotImplementedError`），本项目在应用层用 `CCAgentStorage`（`backend/storage.py`）子类补齐了它们，并定义独立的 `ChannelRow` 表随 `create_tables=True` 自动建表，故渠道在 SQLite 后端下可正常使用。真正接通平台还需配置 bot 凭证；`RedisMessageBus` 提供 dispatcher/gateway 所需的 pubsub/锁/队列。Web UI 经 HTTP API 直连后端，本身不依赖渠道。

## 环境要求

开始前请确认本机已具备：

- **Python ≥ 3.13** + [uv](https://docs.astral.sh/uv/)
- **Node.js ≥ 20** + **pnpm**（browser-use MCP 通过 `npx` 启动，依赖 Node）
- **Redis**（消息总线硬依赖，默认 `localhost:6379`）

## 快速开始

### 1. 后端

```bash
# 在仓库根目录
uv sync                              # 按 uv.lock 安装依赖（含本地 agentscope）
cp backend/.env.example backend/.env # 可选：按需修改配置
uv run python -m backend.main        # 启动开发服务：uvicorn 0.0.0.0:8000，热重载
```

首次启动会在 `backend/` 下自动创建 SQLite 文件（默认 `cc_agent.db`），无需手动建表。

### 2. 前端

```bash
cd frontend
pnpm install
pnpm dev      # 启动 Vite 开发服务器
```

打开前端后，首次进入会跳转到 **Setup 页面**：填入后端地址（本地即 `http://localhost:8000`）与用户名，保存后进入主界面。这两个值保存在浏览器 `localStorage`（键名 `server_url`、`username`），之后每次请求都会带上 `X-User-ID` 头。

## 配置说明

后端通过 `backend/.env` 读取配置，不创建则全部使用默认值：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` / `REDIS_PASSWORD` | `localhost` / `6379` / `0` / 空 | Redis 消息总线连接（`REDIS_DB` 为逻辑库索引） |
| `AGENT_DB_NAME` | `cc_agent.db` | SQLite 文件名（相对 `backend/`） |
| `AMAP_API_KEY` | — | 可选，启用高德地图 MCP 服务 |
| `CLAWHUB_API_TOKEN` | — | 可选，技能市场鉴权 |

默认还会装配一个 `browser-use` 的 stdio MCP 服务（`npx @playwright/mcp@latest`）；设置 `AMAP_API_KEY` 后会额外挂载高德地图的 HTTP MCP。

## 开发指南

### 前端约定

- **路径别名**：`@/*` → `frontend/src/*`（`tsconfig.app.json` 与 `vite.config.ts` 中均已配置）。
- **接口封装**：新增后端接口在 `src/api/*` 中编写，统一使用 `src/api/client.ts` 暴露的 `client`；通过 `src/hooks/*` 消费。
- **导入顺序**：ESLint 强制 `import-x/order`（builtin → external → internal → index，组间空行，字母升序）；`src/components/ui/**` 为 shadcn 生成代码，该规则对其关闭，请用 shadcn CLI 重新生成而非手改。
- **国际化**：所有用户可见文案须同时写入 `src/i18n/locales/en.json` 与 `zh.json`（`fallbackLng: en`）。
- **样式**：TailwindCSS 4 + shadcn/ui，类名用 `@/lib/utils` 中的 `cn()` 合并。
- **聊天工具渲染**：每个工具的输出由 `src/components/chat/tool-renderers/` 下对应组件渲染，接入新工具 UI 时新增一个。

常用脚本：

```bash
pnpm dev        # 开发
pnpm build      # 类型检查 + 构建（tsc -b && vite build，也是唯一的类型检查入口）
pnpm lint       # eslint .
pnpm lint:fix
```

### 后端约定

- 入口与所有装配逻辑集中在 `backend/main.py`，修改时注意保留与上游示例的两处差异，避免回退存储 / 消息总线实现。
- 长期记忆基于 `AgenticMemoryMiddleware`，按 agent 隔离，以 Markdown 形式落在会话工作区，跨会话保留。
- 框架 API 的权威实现位于 `agentscope/src/agentscope/`（`app/`、`agent/`、`middleware/`、`mcp/` 等），修改后端行为前应先查阅。

## 许可证

详见仓库根目录相关声明。
