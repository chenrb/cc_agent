# GLM（智谱 AI）模型厂商 接入实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 CC Agent 新增 GLM（智谱 AI）模型厂商，支持 `glm-5.2` 与 `glm-5-turbo`，前端零改动、agentscope 零改动。

**Architecture:** GLM 全部代码置于应用层 `backend/`；`ZhipuChatModel` 继承 `DeepSeekChatModel`（两者 OpenAI 兼容 + `reasoning_content` 思考链机制一致），仅覆盖 `type` 判别符；经 `create_app(extra_credentials=[ZhipuCredential])` 运行时注册进 `CredentialFactory`。模型卡放 backend，由 `ChatModelBase.list_models()` 经 `inspect.getfile(cls)` 自动发现。

**Tech Stack:** Python 3.13、FastAPI、agentscope（内嵌只读副本）、pydantic、pytest（asyncio_mode=auto）、ruff。

## Global Constraints

- **agentscope 目录只读**：禁止修改 `agentscope/` 任何文件；只能 import / 继承。
- **provider type** = `glm_credential`；**model type** = `glm_chat`；schema **title** = `"Zhipu AI (GLM) API"`；**base_url** = `https://open.bigmodel.cn/api/paas/v4`。
- 模型目录固定两个：`glm-5.2`（context 1,000,000 / output 128,000）、`glm-5-turbo`（context 200,000 / output 128,000），均支持 thinking（`output_types` 含 `application/x-thinking`）。
- 前端 / i18n / DashScope 下已有的 `glm-5.2.yaml` 均不改动。
- lint：`uv run ruff check backend`（line-length 100；isort `known-first-party=["backend"]`，`agentscope` 视作第三方且整体排除）。
- 测试：`uv run pytest backend/tests`（conftest 已预置 `JWT_SECRET` / `AGENT_DB_NAME` 环境变量）。
- 提交在 feature 分支进行（当前在 `master`，先开分支）。

---

## File Structure

| 文件 | 操作 | 职责 |
|---|---|---|
| `backend/llm/__init__.py` | 新建 | 包声明：应用层模型厂商扩展入口 |
| `backend/llm/glm/__init__.py` | 新建 | `ZhipuCredential` + `ZhipuChatModel`（继承 DeepSeek） |
| `backend/llm/glm/_models/glm-5.2.yaml` | 新建 | glm-5.2 模型卡（list_models 自动发现） |
| `backend/llm/glm/_models/glm-5-turbo.yaml` | 新建 | glm-5-turbo 模型卡 |
| `backend/app.py` | 修改 | import + `extra_credentials=[ZhipuCredential]` |
| `backend/tests/test_glm.py` | 新建 | 厂商/模型单元测试（无需 Redis/网络） |

> yaml 必须落在定义 `ZhipuChatModel` 的源文件（`backend/llm/glm/__init__.py`）同级 `_models/` 目录，`inspect.getfile(ZhipuChatModel)` 解析到该 `__init__.py`，parent 即 `backend/llm/glm/`，glob `_models/*.yaml` 命中两张卡。

---

## Task 1: 创建 GLM 厂商模块（凭证 + 模型类）

**Files:**
- Create: `backend/llm/__init__.py`
- Create: `backend/llm/glm/__init__.py`
- Test: `backend/tests/test_glm.py`

**Interfaces:**
- Produces: `ZhipuCredential`（`type="glm_credential"`，`get_chat_model_class() -> ZhipuChatModel`）；`ZhipuChatModel`（`type="glm_chat"`，`issubclass(DeepSeekChatModel)`）。

- [ ] **Step 1: 写失败测试**（新建 `backend/tests/test_glm.py`）

```python
from backend.llm.glm import ZhipuChatModel, ZhipuCredential


def test_credential_schema_title_and_discriminator():
    schema = ZhipuCredential.model_json_schema()
    assert schema["title"] == "Zhipu AI (GLM) API"
    assert schema["properties"]["type"]["const"] == "glm_credential"


def test_credential_fields_and_defaults():
    cred = ZhipuCredential(api_key="sk-test")
    assert cred.type == "glm_credential"
    assert cred.api_key.get_secret_value() == "sk-test"
    assert cred.base_url == "https://open.bigmodel.cn/api/paas/v4"


def test_get_chat_model_class_returns_zhipu_model():
    assert ZhipuCredential.get_chat_model_class() is ZhipuChatModel


def test_model_type_and_inheritance():
    from agentscope.model import DeepSeekChatModel

    assert ZhipuChatModel.type == "glm_chat"
    assert issubclass(ZhipuChatModel, DeepSeekChatModel)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_glm.py -v`
Expected: 4 个测试全部 FAIL（`ModuleNotFoundError: No module named 'backend.llm'`）。

- [ ] **Step 3: 实现模块**

新建 `backend/llm/__init__.py`：

```python
"""应用层模型厂商扩展。

CC Agent 不修改内嵌的 agentscope 副本；额外模型厂商在此定义，经
``create_app(extra_credentials=...)`` 在运行时接入。
"""

__all__: list[str] = []
```

新建 `backend/llm/glm/__init__.py`：

```python
# -*- coding: utf-8 -*-
"""Zhipu AI (GLM) 凭证与对话模型。

智谱 GLM 提供 OpenAI 兼容端点（``https://open.bigmodel.cn/api/paas/v4``），
思考链通过 ``reasoning_content`` 返回——与 DeepSeek 完全一致。故 GLM 注册为
应用层厂商：模型类继承 ``DeepSeekChatModel``，仅覆盖 ``type`` 判别符；端点
base_url 由 :class:`ZhipuCredential` 提供，无需修改 agentscope。
"""
from typing import TYPE_CHECKING, Literal, Type

from agentscope.credential import CredentialBase
from agentscope.model import DeepSeekChatModel
from pydantic import ConfigDict, Field, SecretStr

if TYPE_CHECKING:
    from agentscope.model import ChatModelBase

_ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"


class ZhipuCredential(CredentialBase):
    """The Zhipu AI (GLM) credential model."""

    model_config = ConfigDict(
        title="Zhipu AI (GLM) API",
    )

    type: Literal["glm_credential"] = "glm_credential"
    """The credential type."""

    api_key: SecretStr = Field(
        description="The Zhipu AI (GLM) API key.",
    )
    """The API key."""

    base_url: str = Field(
        default=_ZHIPU_BASE_URL,
        description="The base URL for the Zhipu AI (GLM) OpenAI-compatible API.",
    )
    """The base URL for the Zhipu AI (GLM) API."""

    @classmethod
    def get_chat_model_class(cls) -> Type["ChatModelBase"]:
        """Return the ZhipuChatModel class."""
        return ZhipuChatModel


class ZhipuChatModel(DeepSeekChatModel):
    """The Zhipu AI (GLM) chat model.

    GLM 的 OpenAI 兼容端点与思考链机制（``reasoning_content``）均与 DeepSeek
    一致，故继承 ``DeepSeekChatModel`` 全部行为，仅覆盖 ``type`` 判别符；实际
    请求端点由 :class:`ZhipuCredential.base_url` 决定。
    """

    type: Literal["glm_chat"] = "glm_chat"
    """The type of the chat model."""


__all__ = [
    "ZhipuCredential",
    "ZhipuChatModel",
]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_glm.py -v`
Expected: 4 个测试 PASS。

- [ ] **Step 5: lint**

Run: `uv run ruff check backend/llm backend/tests/test_glm.py`
Expected: 无报错（isort：stdlib → agentscope/pydantic 第三方组；`backend` 为 first-party 但本模块即 backend 自身）。

- [ ] **Step 6: 提交**

```bash
git add backend/llm/__init__.py backend/llm/glm/__init__.py backend/tests/test_glm.py
git commit -m "feat(llm): 新增 GLM(智谱) 厂商凭证与对话模型（继承 DeepSeek）"
```

---

## Task 2: 新增模型卡（2 张 yaml）

**Files:**
- Create: `backend/llm/glm/_models/glm-5.2.yaml`
- Create: `backend/llm/glm/_models/glm-5-turbo.yaml`
- Test: 追加到 `backend/tests/test_glm.py`

**Interfaces:**
- Produces: `ZhipuCredential.list_models()` / `ZhipuChatModel.list_models()` 返回两张卡，`name`/`context_size`/`output_types` 符合规格。

- [ ] **Step 1: 写失败测试**（追加到 `backend/tests/test_glm.py` 末尾）

```python
def test_list_models_returns_two_cards_with_specs():
    cards = {c.name: c for c in ZhipuCredential.list_models()}

    assert set(cards) == {"glm-5.2", "glm-5-turbo"}

    glm_52 = cards["glm-5.2"]
    assert glm_52.context_size == 1000000
    assert glm_52.output_size == 128000
    assert "application/x-thinking" in glm_52.output_types

    turbo = cards["glm-5-turbo"]
    assert turbo.context_size == 200000
    assert turbo.output_size == 128000
    assert "application/x-thinking" in turbo.output_types
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_glm.py::test_list_models_returns_two_cards_with_specs -v`
Expected: FAIL（`_models/` 目录不存在 → `list_models` 返回空列表 → `set() == {...}` 断言失败 / AssertionError）。

- [ ] **Step 3: 新建两张模型卡**

`backend/llm/glm/_models/glm-5.2.yaml`（字段参照现有 `agentscope/.../model/_dashscope/_models/glm-5.2.yaml`）：

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
  # Voice 仅适用于 omni 类模型；隐藏该字段避免前端弹窗渲染
  voice:
    hidden: true
```

`backend/llm/glm/_models/glm-5-turbo.yaml`：

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

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest backend/tests/test_glm.py -v`
Expected: 5 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/llm/glm/_models/glm-5.2.yaml backend/llm/glm/_models/glm-5-turbo.yaml backend/tests/test_glm.py
git commit -m "feat(llm): 新增 glm-5.2 / glm-5-turbo 模型卡"
```

---

## Task 3: 在 app.py 注册厂商 + 集成测试 + 全量验证

**Files:**
- Modify: `backend/app.py`（import + `extra_credentials` 参数）
- Test: 追加到 `backend/tests/test_glm.py`

**Interfaces:**
- Produces: 应用启动后 `CredentialFactory._classes` 含 `ZhipuCredential`；`GET /credential/schemas` 出现 GLM；`GET /model/?provider=glm_credential` 返回两张卡。

- [ ] **Step 1: 写失败测试**（追加到 `backend/tests/test_glm.py` 末尾）

```python
def test_credential_factory_registration_round_trip():
    """注册后 CredentialFactory 能按 provider type 反查到 ZhipuCredential，
    且 list_schemas() 含 GLM schema。用快照/恢复避免污染全局注册表。"""
    from agentscope.credential import CredentialFactory

    saved_classes = CredentialFactory._classes[:]
    saved_adapter = CredentialFactory._adapter
    try:
        CredentialFactory.register_credential(ZhipuCredential)
        assert CredentialFactory.get_credential_class("glm_credential") is ZhipuCredential
        schemas = CredentialFactory.list_schemas()
        glm_schema = next(
            (s for s in schemas if s.get("title") == "Zhipu AI (GLM) API"),
            None,
        )
        assert glm_schema is not None
        assert glm_schema["properties"]["type"]["const"] == "glm_credential"
        # 反序列化往返
        cred = CredentialFactory.from_dict(
            {"type": "glm_credential", "api_key": "sk-test"},
        )
        assert isinstance(cred, ZhipuCredential)
    finally:
        CredentialFactory._classes = saved_classes
        CredentialFactory._adapter = saved_adapter
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest backend/tests/test_glm.py::test_credential_factory_registration_round_trip -v`
Expected: 本任务测试在 `register_credential` 后应能通过——**注意**：此测试在 Task 1 已存在的前提下本就会 PASS（注册逻辑在 agentscope，已实现）。它作为回归保护存在；若 PASS 即符合预期，直接进入 Step 3。若想严格 TDD，可先注释掉 `register_credential` 一行观察 FAIL 再恢复。

- [ ] **Step 3: 修改 `backend/app.py`**

在 import 区（`from backend.storage import CCAgentStorage` 附近，保持 isort：`backend` 为 first-party 组）加入：

```python
from backend.llm.glm import ZhipuCredential
```

在 `create_app(...)` 调用（`app.py` 约第 137 行）追加 `extra_credentials` 参数（与其它关键字参数同级）：

```python
        extra_credentials=[ZhipuCredential],
```

完整改动示意（在 `channels=[FeishuChannel, DiscordChannel],` 行之后、`custom_subagent_templates=[...]` 之前插入即可，位置不强制）：

```python
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
            ...
```

- [ ] **Step 4: 运行全量测试确认通过**

Run: `uv run pytest backend/tests -v`
Expected: 全部 PASS（含原有 auth/admin 等测试 + 6 个 GLM 测试）。

- [ ] **Step 5: lint**

Run: `uv run ruff check backend`
Expected: 无报错。

- [ ] **Step 6: 静态自检（不启动服务）**

Run: `uv run python -c "from backend.app import create_application; print('import ok')"`
Expected: 打印 `import ok`（验证 app.py 改动语法/导入正确；此步不连 Redis，仅校验导入链）。若环境无 Redis，`create_application()` 内部不连，仅装配对象，导入应成功。

- [ ] **Step 7: 提交**

```bash
git add backend/app.py backend/tests/test_glm.py
git commit -m "feat(app): 注册 GLM 厂商到 create_app(extra_credentials)"
```

- [ ] **Step 8: 手动验收（需 Redis 运行；可选，由用户执行）**

1. 启动后端：`uv run python -m backend.main`
2. `GET http://localhost:8000/credential/schemas` → 含 `title="Zhipu AI (GLM) API"`、`type.const="glm_credential"`。
3. `GET http://localhost:8000/model/?provider=glm_credential` → 返回 `glm-5.2`、`glm-5-turbo` 两张卡。
4. 前端凭证页"添加凭证"侧栏出现 GLM；填真实智谱 API key 后发起对话，glm-5.2 思考链正常展示。

---

## Self-Review

**1. Spec 覆盖：** spec 第 5.2 节（凭证/模型类）→ Task 1；第 5.2 节模型卡 → Task 2；第 5.3 节 app.py 接线 → Task 3；第 8 节验证 → Task 3 Step 4-8。命名/title/base_url 在 Global Constraints 与 Task 代码中一致。覆盖完整。

**2. 占位符扫描：** 无 TBD/TODO；所有代码块为完整可粘贴内容；测试含真实断言值（1,000,000 / 200,000 / 128,000 / `application/x-thinking`）。

**3. 类型一致性：** `ZhipuCredential`、`ZhipuChatModel`、`glm_credential`、`glm_chat` 在三个任务中拼写一致；`get_chat_model_class` 返回 `ZhipuChatModel`（同模块直接引用，与 spec 修正一致）。

**4. 与实测事实一致：** schema discriminator 形态 `const`（已实测 DeepSeek）；`ChatModelBase` 非 pydantic、`.type` 可直读（已实测）；`CredentialBase.id/name` 有默认值（已读源码）；`list_models` 经 `inspect.getfile` 定位子类同级 `_models/`（已读 `_base.py:127-131`）。
