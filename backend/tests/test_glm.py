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
