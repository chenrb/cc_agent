# AgentScope `examples/` 目录综合技术分析

> 分析目标:`agentscope` 仓库的 `examples/` 目录
> 分析日期:2026-08-07
> 分析范围:`examples/` 下全部子目录(Python 库模式示例 + Web UI 全栈应用)

---

## 1. 执行摘要

`examples/` 目录是 AgentScope 2.x 框架的**官方示例集合**,承担三个职能:

1. **库模式(Library mode)教学** — 用最少代码演示 `agentscope` 核心模块(RAG、长期记忆、Agent)的独立使用方式,不依赖任何服务层。
2. **服务模式(Service mode)参考实现** — `agent_service/main.py` 是一个可直接运行的 FastAPI 后端,展示 `agentscope.app` 的完整能力面(多租户、多会话、权限系统、调度、频道、知识库)。
3. **配套 Web UI** — `web_ui/` 是一个生产级的 React + TypeScript 前端,与上述 FastAPI 后端通过 SSE 流式协议交互,提供聊天、权限审批、调度管理、知识库管理、MCP/Skill 市场、频道(Discord/飞书)等完整 UI。

目录规模一览:

| 子目录 | 角色 | 主要语言 | 文件量级 |
|--------|------|----------|----------|
| `agent_service/` | 服务模式后端入口 | Python | 1 脚本(143 行) |
| `rag/` | RAG 库模式示例 | Python | 2 脚本(381 行) |
| `long_term_memory/` | 长期记忆中间件示例 | Python | 3 脚本(910 行) |
| `workspace/` | 工作区文档 | Markdown | 1 文档 |
| `web_ui/` | 全栈 Web 应用(前端 + 轻量代理后端) | TypeScript / TSX | ~160 个源文件 |

**核心结论**:Python 示例代码量小但信息密度高,每个脚本都对应框架的一个关键扩展点;`web_ui/` 是真正的大头,是一个功能完备、工程化程度高的 SPA,直接反映了 AgentScope 服务层的 API 表面和数据契约。两者通过 `@agentscope-ai/agentscope` 这个 npm 包(发布到 PyPI/JS)共享类型定义,实现了端到端类型安全。

---

## 2. 目录结构总览

```
examples/
├── agent_service/              # FastAPI 服务模式入口
│   ├── main.py                 # create_app() 配置 + uvicorn 启动
│   └── README.md
├── rag/                        # RAG 库模式示例
│   ├── index_and_search.py     # 解析→分块→嵌入→插入→检索
│   ├── integrate_with_agent.py # RAGMiddleware 接入 Agent(static/agentic)
│   └── README.md               # 多向量库后端切换指南(Qdrant/Milvus/Mongo/ES)
├── long_term_memory/           # 三种长期记忆中间件对比
│   ├── agentic_memory/         # 文件系统 Markdown 记忆(内置)
│   │   ├── main.py
│   │   └── README.md
│   ├── mem0/                   # mem0(向量记忆)中间件
│   │   ├── oss_demo.py
│   │   └── README.md
│   └── reme/                   # ReMe(嵌入进程式记忆)中间件
│       ├── reme_demo.py
│       └── README.md
├── workspace/
│   └── apple-container-workspace.md   # AppleContainerWorkspace 用法
└── web_ui/                     # pnpm monorepo 全栈应用
    ├── package.json            # 根 workspace(并发启动 dev)
    ├── pnpm-workspace.yaml     # 声明 frontend + backend 两个包
    ├── .husky/                 # Git hooks(pre-commit)
    ├── backend/                # 极简 Express 代理(健康检查)
    │   ├── src/index.ts        # 仅 /api/health 端点
    │   └── package.json
    └── frontend/               # React 19 + Vite SPA(核心)
        ├── package.json
        ├── vite.config.ts      # 代理 /api → localhost:3000
        └── src/
            ├── api/            # 16 个 API 模块 + 类型定义
            ├── components/     # 100+ TSX 组件(40 个 UI 基础组件)
            ├── hooks/          # 26 个自定义 hooks
            ├── pages/          # 9 个路由页面(chat/schedule/channel/...)
            ├── context/        # Audio + Upload Context
            └── i18n/           # 中英文国际化
```

### 架构层次关系

```
┌─────────────────────────────────────────────────────────┐
│                    用户浏览器                             │
│  web_ui/frontend (React 19 SPA, Vite, Tailwind v4)      │
│  ├─ @agentscope-ai/agentscope (共享类型:Msg / Event)    │
│  └─ SSE 长连接 + REST fetch (X-User-ID 多租户头)         │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────┐
│         agent_service/main.py (FastAPI 后端)             │
│  create_app(storage, message_bus, workspace_manager,     │
│             knowledge_base_manager, channels, ...)       │
│  ├─ RedisStorage          (持久化)                       │
│  ├─ InMemoryMessageBus    (事件总线,可换 Redis)          │
│  ├─ LocalWorkspaceManager (Agent 工作区)                 │
│  ├─ CollectionPerKbManager(知识库, Qdrant 向量库)        │
│  ├─ MCP hubs / Skill hubs (市场)                         │
│  └─ Discord / Feishu Channel(外部平台接入)              │
└────────────────────────┬────────────────────────────────┘
                         │ 库模式直接调用
┌────────────────────────▼────────────────────────────────┐
│            agentscope 核心库 (src/agentscope)            │
│  agent / model / tool / rag / middleware / permission    │
└─────────────────────────────────────────────────────────┘
```

`web_ui/backend/` 在此架构中**不是真正的后端**,只是一个 Express 健康检查代理(`examples/web_ui/backend/src/index.ts:10-12` 仅有 `/api/health`)。真正的后端是 `agent_service/main.py` 启动的 FastAPI 服务(默认 `localhost:8000`)。前端通过 `localStorage.server_url` 动态指向后端地址(`examples/web_ui/frontend/src/api/client.ts:3`)。

---

## 3. 模块逐一深入

### 3.1 `agent_service/` — 服务模式参考实现

**入口**:`examples/agent_service/main.py`(143 行)

这是理解 AgentScope 服务层 API 表面的**最佳入口**。一个 `create_app()` 调用揭示了所有可插拔点:

```python
app = create_app(
    storage=RedisStorage(host="localhost", port=6379),
    message_bus=InMemoryMessageBus(),
    workspace_manager=LocalWorkspaceManager(basedir=..., default_mcps=default_mcps),
    knowledge_base_manager=CollectionPerKbManager(storage=storage, vector_store=vector_store),
    mcp_hubs=[GitHubMCPHub()],
    skill_hubs=[ClawSkillHub(api_token=...)],
    custom_subagent_templates=[SubAgentTemplate(type="explorer", ...)],
    extra_middlewares=[Middleware(CORSMiddleware, ...)],
    channels=[DiscordChannel, FeishuChannel],
)
```

关键设计点:

- **多租户**:`X-User-ID` HTTP 头标识用户(前端 `examples/web_ui/frontend/src/api/client.ts:41`);所有资源(Agent、Session、Credential、KnowledgeBase)按 `user_id` 隔离。
- **MCP 集成**:`default_mcps` 展示了 Stdio(playwright)和 HTTP(高德地图)两种 MCP 接入方式(`examples/agent_service/main.py:20-41`)。
- **子代理模板**:`SubAgentTemplate` 定义团队(team)中可创建的子代理类型,这里定义了一个只读 `explorer` 角色,绑定 `PermissionMode.EXPLORE` 权限(`examples/agent_service/main.py:84-120`)。
- **频道接入**:Discord 和飞书作为外部消息入口,通过路由规则映射到 Agent 会话。
- **可扩展性**:`extra_middlewares` 和注释中展示的 `RedisMessageBus` 替换路径,说明生产部署的演进方向。

### 3.2 `rag/` — RAG 库模式示例

两个脚本互补,共同覆盖 RAG 的两条路径:

#### `index_and_search.py`(183 行)— 最小化索引检索管线

```
bytes ── TextParser ──► Section[] ── ApproxTokenChunker ──► Chunk[]
                                                              │
                            KnowledgeBase.insert_document ◄──┘
                                  (embed → Qdrant)
                                  │
KnowledgeBase.search(queries) ──► VectorSearchResult[]
```

- 5 个核心积木:`QdrantStore`、`TextParser`、`ApproxTokenChunker`、`DashScopeEmbeddingModel`、`KnowledgeBase`(`examples/rag/index_and_search.py:147-169`)。
- 使用 `location=":memory:"` 的 Qdrant,零外部依赖;`DashScope text-embedding-v4`(1024 维)。
- 文档以 bytes 内联,避免磁盘依赖,保证示例可一键运行。

#### `integrate_with_agent.py`(198 行)— RAGMiddleware 两种模式

同一知识库挂到两个 Agent,展示中间件控制策略:

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| `static` | 首个推理步骤自动检索,以 `HintBlock` 一次性注入(用后即删) | 用户希望模型无感地获得上下文 |
| `agentic`(默认) | 暴露 `search_knowledge` 工具,由模型决定何时检索 | 模型自主决策,多知识库场景 |

关键代码(`examples/rag/integrate_with_agent.py:159-185`):
```python
static_mw = RAGMiddleware(
    knowledge_bases=[knowledge],
    parameters=RAGMiddleware.Parameters(mode="static", top_k=3, emit_hint_event=False),
)
agentic_mw = RAGMiddleware(
    knowledge_bases=[knowledge],
    parameters=RAGMiddleware.Parameters(mode="agentic", top_k=3),
)
```

README 还提供了**向量库后端切换矩阵**(`examples/rag/README.md:231-237`):Qdrant(默认内存)、Milvus Lite(本地持久化)、MongoDB(Atlas)、Elasticsearch,各有独立可选依赖 `agentscope[vdb-*]`。

### 3.3 `long_term_memory/` — 三种记忆中间件对比

这是 examples 中**信息密度最高**的部分,三个并排实现揭示了一个关键设计维度:**记忆的控制权归属**。

#### 共同的控制模式抽象

三种中间件都遵循同一套 `mode` 枚举(`examples/long_term_memory/mem0/README.md:122-172`):

| `mode` | 谁检索 | 谁写入 | 暴露工具 |
|--------|--------|--------|----------|
| `static_control` | 中间件自动(注入 HintBlock) | 中间件自动 | 否 |
| `agent_control` | Agent 显式调用工具 | Agent 显式调用工具 | 是 |
| `both`(默认) | 自动 + 工具并存 | 自动 + 工具并存 | 是 |

#### 三者差异

| 维度 | `AgenticMemoryMiddleware` | `Mem0Middleware` | `ReMeMiddleware` |
|------|---------------------------|------------------|------------------|
| 后端 | 本地 Markdown 文件 | mem0(OSS Qdrant / Platform) | ReMe(嵌入进程) |
| 依赖 | 无(仅 AgentScope) | `agentscope[memory-mem0]` | `agentscope[memory-reme]` |
| 向量库 | 无(关键词 + 文件名) | Qdrant(默认 `/tmp/qdrant`) | 可选(注入 embedding_model 启用) |
| 写入触发 | Agent 用 Read/Write 工具写文件 | 中间件自动 + add_memory 工具 | **始终自动**(auto_memory,监听对话) |
| 隔离维度 | workspace 目录 | `user_id` × `agent_id` | `session_id`(搜索跨 session) |
| 跨实例共享 | 通过共享 workdir | 共享 middleware 实例(Qdrant 锁!) | 共享 middleware 实例(安全) |

**值得注意的工程细节**:

1. **mem0 的 Qdrant 锁陷阱**(`examples/long_term_memory/mem0/README.md:176-216`):本地 on-disk Qdrant 对存储目录加**独占锁**,两个 `Mem0Middleware` 实例各自构造 `AsyncMemory` 会崩。解决方案是**共享一个 middleware 实例**,或用 Docker 跑 Qdrant。Windows 上文件锁语义不同,尤其脆弱。

2. **ReMe 的 `session_id` 设计**(`examples/long_term_memory/reme/README.md:136-152`):写入按 `session_id`(从 `agent.state.session_id` 实时读取)隔离,但**搜索跨整个 workspace** —— 这正是跨 session 记忆恢复的机制。demo 用 `session-1` 写入、`session-2`(全新 Agent,空上下文)检索来验证。

3. **AgenticMemoryMiddleware 的 Markdown 布局**(`examples/long_term_memory/agentic_memory/README.md:47-75`):`MEMORY.md` 是索引(始终注入 system prompt),具体记忆在带 frontmatter 的独立 `.md` 文件中。这种设计让记忆**可读、可编辑、可 git 提交**。

4. **事件流驱动**:`mem0/oss_demo.py` 和 `reme/reme_demo.py` 都通过 `agent.reply_stream` 消费事件流,在 `ReplyStartEvent`、`ToolCallStartEvent`、`TextBlockDeltaEvent` 等节点打印中间件贡献,展示了 AgentScope 的事件驱动架构。

### 3.4 `web_ui/` — 生产级全栈前端

这是 examples 目录的**重头戏**,代码量占 90% 以上。

#### 技术栈

- **框架**:React 19 + React Router 7(数据路由)+ Vite 8
- **UI**:Tailwind CSS v4 + shadcn/ui + Radix UI + Lucide 图标
- **状态**:自定义 hooks(无 Redux/Zustand),基于 `useCallback` + `useRef` + `requestAnimationFrame` 批量更新
- **流式**:`@agentscope-ai/agentscope` SDK 提供 `Msg` / `AgentEvent` 类型,SSE 长连接消费
- **国际化**:i18next + react-i18next(中/英)
- **工程化**:pnpm workspace + Husky pre-commit + lint-staged + ESLint + Prettier
- **富文本**:streamdown(markdown)+ react-diff-view(代码 diff)+ mermaid 图表

#### 入口与路由

`examples/web_ui/frontend/src/main.tsx` → `App.tsx`(`examples/web_ui/frontend/src/App.tsx:33-64`):

```
/                  → 重定向到 /chat
/chat/:agentId?/:sessionId?/:memberId?   → ChatPage(三段 URL 驱动状态)
/schedule          → 定时任务管理
/channel           → 频道(Discord/飞书)管理
/credential        → 凭证管理
/mcp(/:hubId)      → MCP 市场
/skill(/:hubId)    → Skill 市场
/knowledge(/:kbId) → 知识库管理
/setup             → 首次配置(输入后端地址)
```

**关键设计**:URL 是唯一状态源。`ChatPage` 的注释明确说明(`examples/web_ui/frontend/src/pages/chat/index.tsx:60-78`):"every selection is a `navigate(...)` call. State is derived from `useParams`, never duplicated in React state." 这带来了浏览器前进/后退、可分享链接、刷新保持状态等好处。

#### API 层与类型契约

`examples/web_ui/frontend/src/api/types.ts`(1048 行)是**前后端契约的权威定义**,覆盖 15+ 个领域:Agent、Session、Team、Credential、Chat、MCP、Skill、Hub、Schedule、Model、Embedding、KnowledgeBase、Channel、TTS、Health。

核心 API 客户端(`examples/web_ui/frontend/src/api/client.ts`):
- `getBaseUrl()` / `getUserId()` 从 `localStorage` 读取 → 支持任意后端地址
- 每个 request 自动注入 `X-User-ID` 头(多租户)
- `ApiError` 封装,自动 toast 错误(除非 `silent: true`)
- `stream()` 方法返回原始 `Response`,供 SSE 消费

#### 核心数据流:聊天

`useMessages` hook(`examples/web_ui/frontend/src/hooks/useMessages.ts`,492 行)是整个前端最复杂的 hook,管理**双通道事件交付**:

```
                 ┌─ History: GET /sessions/{sid}/messages (持久化 Msg[])
                 │
useMessages ─────┤
                 │   ┌─ ReplyStartEvent → 新建 AssistantMsg
                 └─ Live: GET /sessions/{sid}/stream (SSE) ─┤
                     │   TextBlockDeltaEvent → 追加文本
                     │   ToolCallStartEvent → 工具调用卡片
                     │   RequireUserConfirmEvent → HITL 卡片
                     │   DataBlockStart/Delta/End → 音频流
                     │   ReplyEndEvent → phase 回 idle
                     │   CustomEvent(team_updated/state_updated/...) → 回调
                     └─ requestAnimationFrame 批量刷新 UI
```

关键状态机 `phase: 'idle' | 'streaming' | 'interrupting'`(`examples/web_ui/frontend/src/hooks/useMessages.ts:59-76`):
- 由事件内容驱动,非 HTTP 生命周期
- `streaming`:从 `ReplyStartEvent` 到 `ReplyEndEvent`
- `interrupting`:用户点击 Stop 后,等待终止事件;10 秒安全超时回退

**HITL(人机回环)**:`onUserConfirm` 通过 `POST /chat/` 发送 `UserConfirmResultEvent`;**子代理 HITL** 通过 `CustomEvent(name="subagent_require_user_confirm")` 从 worker session 投射到 leader view,前端**只 POST 到 leader**,后端路由到 worker(`examples/web_ui/frontend/src/hooks/useMessages.ts:442-477`)。

#### 页面功能矩阵

| 页面 | 核心功能 | 对应后端 API |
|------|----------|-------------|
| Chat | 消息、工具调用渲染、HITL、权限模式切换、TTS、团队侧栏、Tour 引导 | `/chat/`、`/sessions/`、SSE |
| Schedule | Cron 定时任务、日历视图、列表视图、会话审计 | `/schedule/` |
| Channel | Discord/飞书频道绑定、路由规则编辑、连接状态 | `/channels/` |
| Credential | 模型凭证 CRUD(按 provider 分组) | `/credentials/` |
| MCP | MCP 市场浏览、安装、配置、健康状态 | `/mcp/`、`/hub/` |
| Skill | Skill 市场浏览、安装、查看 SKILL.md | `/skill/`、`/hub/` |
| Knowledge | 知识库 CRUD、文档上传、索引状态轮询、语义检索测试 | `/knowledge_bases/` |

#### 工具调用渲染器

`examples/web_ui/frontend/src/components/chat/tool-renderers/` 针对每种工具定制渲染:
- `BashRenderer`、`ReadRenderer`、`WriteRenderer`、`EditRenderer`(带 `DiffPreview`)
- `GrepRenderer`、`GlobRenderer`、`TaskCreateRenderer`
- `DefaultRenderer`(兜底)+ `_shared.tsx`(共享样式)

这表明 Web UI 主要面向**编码类 Agent**场景(文件操作工具的可视化)。

---

## 4. 架构模式评估

### 4.1 双模式架构(Library vs Service)

AgentScope 明确区分两种使用模式,examples 直接对应:

| | Library mode | Service mode |
|---|---|---|
| 对应示例 | `rag/`、`long_term_memory/` | `agent_service/` + `web_ui/` |
| 进程模型 | 单进程,用户直接 `asyncio.run(main())` | FastAPI 多进程 + SSE |
| 状态管理 | 用户自管(`AgentState`、`workdir`) | `RedisStorage` 持久化 |
| 适用场景 | 脚本、原型、学习 | 生产部署、多租户、Web 接入 |

### 4.2 中间件驱动的可组合性

所有扩展能力(RAG、mem0、ReMe、agentic_memory)都以**中间件**形式接入 Agent。这是 AgentScope 的核心架构选择:

```python
agent = Agent(
    ...,
    middlewares=[rag_mw, mem0_mw, agentic_mem_mw],  # 自由组合
)
```

中间件通过生命周期钩子(`on_reply` pre/post、`on_reasoning`)介入推理循环,三种记忆中间件的 `mode` 枚举证明了这套钩子足够灵活。

### 4.3 事件流协议(SSE + AgentEvent)

前后端通过**统一的 `AgentEvent` 类型**通信,由 `@agentscope-ai/agentscope` npm 包共享:
- 前端 `import { AgentEvent } from '@agentscope-ai/agentscope/event'`
- 后端 Python `agentscope.event` 模块
- SSE 流式推送,前端 `for await (const event of sessionApi.streamEvents(...))` 消费

这保证了类型安全和协议一致性。

---

## 5. 工程质量评估

### 5.1 优点

1. **文档与代码并重**:每个子目录都有详尽 README,`rag/README.md` 甚至覆盖 4 种向量库后端的切换;`mem0/README.md` 包含完整的参数优先级矩阵(`examples/long_term_memory/mem0/README.md:98-109`)。

2. **类型安全到前端**:`types.ts` 的 JSDoc 注释异常详尽,解释了每个字段的设计理由(如 `KnowledgeDocumentStatus` 的生命周期、`editable` 字段的权限语义)。

3. **可复现性**:示例脚本普遍提供"clean slate"逻辑(`RESET_DEMO_WORKSPACE`、清理 `/tmp/qdrant`、`mkdtemp`),保证多次运行结果一致。

4. **i18n 完整**:`zh.json` + `en.json`,所有 UI 文案走 `t('...')`。

5. **渐进式复杂度**:从最简单的 `index_and_search.py`(5 个积木)到最复杂的 `useMessages.ts`(双通道 SSE + 状态机),覆盖全频谱。

### 5.2 潜在风险点

1. **`web_ui/backend/` 定位模糊**:它只是一个 `/api/health` 代理,容易误导读者以为这是真后端。实际后端是 `agent_service/main.py`(端口 8000),而 `web_ui/backend` 默认端口 3000,前端 vite proxy 指向 3000(`examples/web_ui/frontend/vite.config.ts:12`)。两者关系需要从 README 交叉阅读才能厘清。

2. **密钥管理**:示例依赖环境变量(`DASHSCOPE_API_KEY`、`AMAP_API_KEY`、`CLAWHUB_API_TOKEN`),`main.py:36` 直接用 f-string 拼接 URL —— 虽然是 demo,但生产场景应避免。

3. **平台耦合**:Python 长期记忆示例有明显的 Unix 偏向(`/tmp/qdrant`、`~/.mem0/history.db`),README 已明确警告 Windows 用户用 Docker,但代码层面未做抽象。

4. **前端复杂度**:100+ 组件、26 个 hooks,对于一个 "example" 来说体量庞大。没有看到测试文件(e2e 或单元),依赖人工验证。

---

## 6. 运行与部署

### 6.1 Python 示例

```bash
# 通用前置
uv pip install "agentscope[full]"   # 或 [rag] / [memory-mem0] / [memory-reme]
export DASHSCOPE_API_KEY=sk-...

# RAG
python examples/rag/index_and_search.py
python examples/rag/integrate_with_agent.py

# 长期记忆
cd examples/long_term_memory/agentic_memory && python main.py
python examples/long_term_memory/mem0/oss_demo.py
python examples/long_term_memory/reme/reme_demo.py
```

### 6.2 服务模式 + Web UI

```bash
# 1. 启动 Redis
docker run --rm -p 6379:6379 redis:7

# 2. 启动后端
cd examples/agent_service && python main.py   # → localhost:8000

# 3. 启动前端
cd examples/web_ui && pnpm install && pnpm dev  # → localhost:5173(默认)
```

在 Web UI 首次访问时,Setup 页面要求输入 `server_url`(填 `http://localhost:8000`)和 `username`。

### 6.3 CI/工程化

`web_ui/` 配备:
- Husky pre-commit(`.husky/`)
- lint-staged(Prettier + ESLint on TSX/TS/JSON/MD)
- `pnpm format` / `pnpm format:check` 统一格式
- `pnpm build` 分前后端独立编译

---

## 7. 值得进一步关注

1. **`agentscope.app` 的路由定义**:examples 只展示 `create_app()` 的配置面,实际 REST 路由(`/chat/`、`/sessions/{id}/stream` 等)定义在 `src/agentscope/app/` 下,值得对照前端 `api/` 模块逐一阅读。

2. **事件协议的 Python 端**:`AgentEvent` 的 Python 定义和 SSE 序列化逻辑在 `src/agentscope/event`,是理解流式聊天端到端的关键。

3. **权限系统**:`PermissionMode`(default/accept_edits/explore/bypass/dont_ask)在前端 `types.ts:621-627` 只是枚举,实际执行逻辑(`PermissionContext`、工具调用拦截)在 `src/agentscope/permission/`。

4. **Workspace 抽象**:`workspace/apple-container-workspace.md` 揭示了 `AppleContainerWorkspace`(Apple Container VM 隔离),与 `LocalWorkspaceManager` 形成对比 —— 这是 AgentScope 工具执行沙箱的核心抽象。

5. **npm 包 `@agentscope-ai/agentscope`**:前端依赖 `^0.0.15`,提供 `Msg`/`AgentEvent`/`appendEvent` 等。这个包的发布流程和 Python 包的关系(是否同源生成?)值得考察。
