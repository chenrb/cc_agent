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
