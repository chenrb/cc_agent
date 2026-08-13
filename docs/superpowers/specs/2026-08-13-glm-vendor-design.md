# 设计：新增 GLM（智谱 AI）模型厂商

- **日期**：2026-08-13
- **状态**：已批准，待实现
- **范围**：为 CC Agent 新增 GLM（智谱 AI / Zhipu）作为可选模型厂商，支持 `glm-5.2` 与 `glm-5-turbo` 两个模型

## 1. 背景与动机

CC Agent 是基于 AgentScope 框架的前后端分离智能体应用。模型厂商（provider）体系是 **schema 驱动** 的：

- 前端无任何硬编码厂商列表。厂商清单、API key 表单、模型卡全部由后端动态下发：
  - `GET /credential/schemas` → 渲染厂商选择下拉框 + 凭证表单
  - `GET /model/?provider=<type>` → 返回该厂商的模型卡
- 唯一的厂商注册表在后端：`agentscope/src/agentscope/credential/_factory.py` 的 `CredentialFactory._classes`。
- 当前内置 8 个厂商：Anthropic、DashScope、DeepSeek、Gemini、Moonshot、Ollama、OpenAI、xAI。GLM **不是** 独立厂商，仅作为 DashScope 中转下的一个模型卡存在（`model/_dashscope/_models/glm-5.2.yaml`）。

目标：把 GLM 作为**独立厂商**接入，用户在控制台填入智谱 API key 后即可直连智谱端点使用 GLM 模型（含思考链、工具调用）。

## 2. 关键约束

- **agentscope 目录只读，禁止修改**（用户明确要求）。所有 GLM 代码必须放在应用层 `backend/`。agentscope 只能被 **导入 / 继承**，不能被修改。
- 模型目录固定为两个：`glm-5.2`、`glm-5-turbo`。
- GLM（智谱）提供 **OpenAI 兼容端点** `https://open.bigmodel.cn/api/paas/v4`，可直接复用 OpenAI SDK 调用。两个模型的思考链均通过 `reasoning_content` 字段返回，启用方式为请求体 `extra_body.thinking.type = "enabled"`——与 DeepSeek 的实现**完全一致**。

## 3. 模型规格（已与用户确认，数据来源：智谱官方文档）

| 字段 | glm-5.2 | glm-5-turbo |
|---|---|---|
| label | GLM 5.2 | GLM 5 Turbo |
| 调用 model 名 | `glm-5.2` | `glm-5-turbo` |
| context_size | 1,000,000 | 200,000 |
| output_size | 128,000 | 128,000 |
| 支持 thinking | 是（`reasoning_content`） | 是（`reasoning_content`） |
| 输入类型 | 仅 `text/plain`（不支持多模态） | 仅 `text/plain` |
| 工具调用 | 支持 | 支持 |
| max_tokens 上限 | 128,000 | 128,000 |

参考：[GLM-5-turbo 文档](https://docs.bigmodel.cn/cn/guide/models/text/glm-5-turbo)、[OpenAI 兼容说明](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction)。

## 4. 方案选择

| | A. agentscope 内新增（克隆 DeepSeek） | **B. backend 应用层注册（继承 DeepSeek）** | C. 复用 OpenAI 厂商 + 自定义 base_url |
|---|---|---|---|
| 是否改 agentscope | 是（违反约束） | **否** | 否 |
| 模型卡可见 | ✅ | ✅ | ❌ OpenAI 列表无 GLM |
| 厂商标题正确 | ✅ | ✅ | ❌ 显示成 OpenAI |
| thinking/工具 | ✅ | ✅ | ⚠️ 参数对不上 |
| 代码量 | 大（克隆 ~480 行 wrapper） | **小（继承，仅覆盖 type）** | 零代码 |
| 结论 | ✗ 违反约束 | **✅ 采用** | ✗ UX 差 |

**采用方案 B**。机制：`create_app(extra_credentials=[ZhipuCredential])` 在运行时把厂商注册进 `CredentialFactory`（见 `agentscope/src/agentscope/app/_app.py:270-271`），无需改动 agentscope 任何文件。

### 4.1 为什么继承而非克隆

- `ZhipuChatModel(DeepSeekChatModel)` 只覆盖 `type: Literal["glm_chat"]`，即可继承 DeepSeek 的全部行为：thinking 启用、`reasoning_content` 流式 / 非流式解析、工具调用格式化、structured-output 的 thinking 降级处理。
- `base_url` 来自 credential 实例（智谱端点），`DeepSeekChatModel.__init__` 读 `self.credential.base_url`，传入 `ZhipuCredential` 即自动指向智谱。
- formatter 由 `DeepSeekChatModel.__init__` 默认装配为 `DeepSeekChatFormatter`，消息格式字节级一致，**零额外 formatter 代码**。
- 已核实：`ChatModelBase.type` 是普通类属性（`__init__` 不校验），子类覆盖合法；`ChatModelBase.list_models()` 用 `inspect.getfile(cls)` 按**具体子类的源文件**定位 `_models/*.yaml`（`model/_base.py:127-131`），故 backend 内的 yaml 可被自动发现。

### 4.2 为什么 formatter 不单独建文件

每个厂商的消息格式各厂的 formatter 处理 `reasoning_content` 必填、HintBlock/ToolResult 刷新等逻辑。GLM 与 DeepSeek 格式完全一致，复用 `DeepSeekChatFormatter`（随继承自动装配）避免 ~300 行冗余克隆。若将来 GLM 格式与 DeepSeek 分叉，再独立建 `GLMChatFormatter`。

## 5. 详细设计

### 5.1 命名约定（对齐 `deepseek_credential` / `deepseek_chat`）

| 项 | 值 |
|---|---|
| provider type（discriminator） | `glm_credential` |
| model type | `glm_chat` |
| 凭证类 | `ZhipuCredential` |
| 模型类 | `ZhipuChatModel` |
| schema title（前端显示名） | `"Zhipu AI (GLM) API"` |
| 默认 base_url | `https://open.bigmodel.cn/api/paas/v4` |

### 5.2 新增文件（backend，4 个）

```
backend/llm/__init__.py              # 空包，声明 backend.llm 为应用层模型厂商扩展
backend/llm/glm/__init__.py          # ZhipuCredential + ZhipuChatModel
backend/llm/glm/_models/glm-5.2.yaml
backend/llm/glm/_models/glm-5-turbo.yaml
```

**`backend/llm/glm/__init__.py`** 核心内容：

- `ZhipuCredential(CredentialBase)`：
  - `model_config = ConfigDict(title="Zhipu AI (GLM) API")`
  - `type: Literal["glm_credential"] = "glm_credential"`
  - `api_key: SecretStr`（描述 "The Zhipu AI (GLM) API key."）
  - `base_url: str` 默认 `https://open.bigmodel.cn/api/paas/v4`
  - `get_chat_model_class()` 返回 `ZhipuChatModel`
- `ZhipuChatModel(DeepSeekChatModel)`：
  - `type: Literal["glm_chat"] = "glm_chat"`
  - 不覆盖其它任何成员。

实现要点：
- 仿 `agentscope/src/agentscope/credential/_deepseek.py`（42 行）的凭证结构。
- 模型类导入：`from agentscope.model import DeepSeekChatModel`；凭证基类 `from agentscope.credential import CredentialBase`。
- `ZhipuCredential` 与 `ZhipuChatModel` 同处一个模块（`backend/llm/glm/__init__.py`），`get_chat_model_class` 直接 `return ZhipuChatModel` 即可，无需 import。（DeepSeek 用局部 import 是因为它的凭证与模型分处两个模块；此处不同。）

**模型卡 YAML**（仿 `model/_dashscope/_models/glm-5.2.yaml`）：

`glm-5.2.yaml`：
```yaml
name: glm-5.2
label: GLM 5.2
status: active
input_types:
  - text/plain
output_types:
  - text/plain
  - application/x-thinking
context_size: 1000000
output_size: 128000
parameter_overrides:
  max_tokens: {"maximum": 128000}
  voice:
    hidden: true
```

`glm-5-turbo.yaml`：
```yaml
name: glm-5-turbo
label: GLM 5 Turbo
status: active
input_types:
  - text/plain
output_types:
  - text/plain
  - application/x-thinking
context_size: 200000
output_size: 128000
parameter_overrides:
  max_tokens: {"maximum": 128000}
  voice:
    hidden: true
```

### 5.3 修改文件（backend，1 个）

`backend/app.py`：
- 顶部 `from backend.llm.glm import ZhipuCredential`
- `create_app(...)` 调用（当前在 `app.py:137`）增加参数：`extra_credentials=[ZhipuCredential]`

### 5.4 不改动

- **agentscope/**：零改动（只读依赖）。
- **frontend/**：零改动。新厂商通过 `/credential/schemas` 自动出现在"添加凭证"侧栏；模型卡通过 `/model/?provider=glm_credential` 自动渲染。
- **i18n（en.json / zh.json）**：零改动。厂商名来自后端 schema 的 `title`，模型名来自 YAML 的 `label`，无厂商专属文案。
- **DashScope 下的 `glm-5.2.yaml`**：保留不动。它代表"经 DashScope 中转访问 GLM-5.2"，与本厂商"智谱直连"是两条独立链路；模型卡按 provider 隔离，互不冲突。

## 6. 数据流

1. 应用启动 → `create_application()` → `create_app(extra_credentials=[ZhipuCredential])` → `CredentialFactory.register_credential(ZhipuCredential)`，`glm_credential` 进入 `_classes`。
2. 前端进入凭证页 → `GET /credential/schemas` → 返回含 `ZhipuCredential` 的 schema（title "Zhipu AI (GLM) API"，type `glm_credential`）。
3. 用户选 GLM、填 API key → 前端 POST 创建凭证（`type=glm_credential`）。
4. 选中 GLM 凭证 → `GET /model/?provider=glm_credential` → `CredentialFactory.get_credential_class("glm_credential")` → `ZhipuCredential.get_chat_model_class()` → `ZhipuChatModel.list_models()` → glob `backend/llm/glm/_models/*.yaml` → 返回 glm-5.2、glm-5-turbo 两张卡。
5. 发起对话 → 模型服务 `CredentialFactory.from_dict(data)` 反序列化为 `ZhipuCredential` → 实例化 `ZhipuChatModel(credential, model, ...)` → `DeepSeekChatModel.__init__` 用 `openai.AsyncClient(api_key=..., base_url=智谱端点)` 发请求；thinking/工具调用按 DeepSeek 同款逻辑处理。

## 7. 错误处理与回退

- 复用 `DeepSeekChatModel` 的重试逻辑（`_get_retryable_exceptions` 返回 openai 的连接 / 超时 / 限流 / 5xx）。
- 智谱端点鉴权失败、限流等错误由 openai SDK 抛出，沿用既有错误处理路径，不新增分支。
- `list_models` 对单个 yaml 解析失败有 `try/except` + warning 兜底（`_base.py:147-154`），不会因一张坏卡阻塞整个列表。

## 8. 测试与验证

无新增单测框架改动（应用层薄）。验证方式：

1. 启动后端（`uv run python -m backend.main`，需 Redis 已运行）。
2. `GET /credential/schemas` 响应中包含 `type.const == "glm_credential"`、`title == "Zhipu AI (GLM) API"`。
3. `GET /model/?provider=glm_credential` 返回 `glm-5.2`、`glm-5-turbo` 两张卡，字段与第 3 节规格一致。
4. 前端凭证页"添加凭证"侧栏出现 GLM；填入真实智谱 API key 后能发起对话，glm-5.2 的思考链正常展示。
5. lint：`uv run ruff check backend`（配置排除 `agentscope/`，只检查 backend 新增文件）。

## 9. 风险与备注

- **继承耦合**：`ZhipuChatModel` 依赖 `DeepSeekChatModel` 的内部行为。若上游 DeepSeek 实现发生 DeepSeek 专属偏移，GLM 可能受影响。缓解：GLM 与 DeepSeek 同为 OpenAI 兼容 + reasoning_content，行为本应一致；分叉时再独立克隆。
- **模型规格时效**：`output_size=128000`、context 等以智谱 2026-08 文档为准，后续若官方调整需同步 yaml。
- **未来扩展**：若新增第二个应用层厂商，应为其建独立子包（如 `backend/llm/<vendor>/`），避免共用 `_models/` 目录导致 `list_models` 跨厂商混入（`list_models` glob 的是子类源文件同级的整个 `_models/`）。
