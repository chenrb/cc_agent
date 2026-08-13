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


def test_credential_factory_registration_round_trip():
    """注册后 CredentialFactory 能按 provider type 反查到 ZhipuCredential，
    且 list_schemas() 含 GLM schema；from_dict 可反序列化。用快照/恢复避免
    污染全局注册表。"""
    from agentscope.credential import CredentialFactory

    saved_classes = CredentialFactory._classes[:]
    saved_adapter = CredentialFactory._adapter
    try:
        CredentialFactory.register_credential(ZhipuCredential)
        assert CredentialFactory.get_credential_class("glm_credential") is ZhipuCredential
        glm_schema = next(
            (s for s in CredentialFactory.list_schemas() if s.get("title") == "Zhipu AI (GLM) API"),
            None,
        )
        assert glm_schema is not None
        assert glm_schema["properties"]["type"]["const"] == "glm_credential"
        cred = CredentialFactory.from_dict(
            {"type": "glm_credential", "api_key": "sk-test"},
        )
        assert isinstance(cred, ZhipuCredential)
    finally:
        CredentialFactory._classes = saved_classes
        CredentialFactory._adapter = saved_adapter
