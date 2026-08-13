"""Zhipu AI (GLM) 凭证与对话模型。

智谱 GLM 提供 OpenAI 兼容端点（``https://open.bigmodel.cn/api/paas/v4``），
思考链通过 ``reasoning_content`` 返回——与 DeepSeek 完全一致。故 GLM 注册为
应用层厂商：模型类继承 ``DeepSeekChatModel``，仅覆盖 ``type`` 判别符；端点
base_url 由 :class:`ZhipuCredential` 提供，无需修改 agentscope。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

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
    def get_chat_model_class(cls) -> type[ChatModelBase]:
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
