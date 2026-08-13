"""app.llm.gemini_api.GeminiAPIProvider에 대한 테스트.

실제 google-genai SDK/네트워크에 의존하지 않도록, 생성자에 fake client를
직접 주입해서(`client=...`) 검증한다.
"""

from unittest.mock import MagicMock

import pytest

from app.llm.gemini_api import GeminiAPIError, GeminiAPIProvider


def _fake_client(response_text="hello", side_effect=None):
    client = MagicMock()
    if side_effect is not None:
        client.models.generate_content.side_effect = side_effect
    else:
        client.models.generate_content.return_value = MagicMock(text=response_text)
    return client


def test_generate_returns_response_text_on_success():
    client = _fake_client(response_text="hi there")
    provider = GeminiAPIProvider(client=client)

    result = provider.generate("hello")

    assert result == "hi there"
    client.models.generate_content.assert_called_once()


def test_constructor_raises_without_api_key_or_client():
    with pytest.raises(GeminiAPIError):
        GeminiAPIProvider()


def test_client_exception_is_wrapped_as_gemini_api_error():
    client = _fake_client(side_effect=RuntimeError("network down"))
    provider = GeminiAPIProvider(client=client)

    with pytest.raises(GeminiAPIError, match="network down"):
        provider.generate("hello")


def test_response_without_text_raises_gemini_api_error():
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=None)
    provider = GeminiAPIProvider(client=client)

    with pytest.raises(GeminiAPIError):
        provider.generate("hello")


def test_response_with_empty_string_text_raises_gemini_api_error():
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text="")
    provider = GeminiAPIProvider(client=client)

    with pytest.raises(GeminiAPIError):
        provider.generate("hello")


def test_system_prompt_is_passed_in_config():
    client = _fake_client()
    provider = GeminiAPIProvider(client=client)

    provider.generate("hello", system="you are concise")

    _, kwargs = client.models.generate_content.call_args
    assert kwargs["config"]["system_instruction"] == "you are concise"


def test_config_omits_system_instruction_when_not_given():
    client = _fake_client()
    provider = GeminiAPIProvider(client=client)

    provider.generate("hello")

    _, kwargs = client.models.generate_content.call_args
    assert "system_instruction" not in kwargs["config"]


def test_temperature_is_passed_in_config():
    client = _fake_client()
    provider = GeminiAPIProvider(client=client)

    provider.generate("hello", temperature=0.2)

    _, kwargs = client.models.generate_content.call_args
    assert kwargs["config"]["temperature"] == 0.2
