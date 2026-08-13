"""llm.factory.get_llm_provider()에 대한 테스트.

get_llm_provider(env=...)에 dict를 넘겨서 실제 환경변수/.env 파일에
영향을 주지 않고 테스트한다. GeminiAPIProvider 생성 자체는 google-genai
Client 객체를 만들 뿐 네트워크 호출을 하지 않으므로 별도 모킹 없이도
안전하게 테스트할 수 있다 (실제 generate() 호출은 별도 테스트 파일에서
client를 모킹해 검증한다). claude CLI의 존재 여부는 실제 PATH 상태에
의존하지 않도록 ClaudeCLIProvider.is_available을 모킹한다.
"""

from unittest.mock import patch

import pytest

from llm.claude_cli import ClaudeCLIProvider
from llm.factory import LLMConfigError, get_llm_provider
from llm.gemini_api import GeminiAPIProvider


def test_explicit_gemini_api_with_key_returns_gemini_provider():
    env = {"LLM_PROVIDER": "gemini_api", "GEMINI_API_KEY": "fake-key"}
    provider = get_llm_provider(env=env)
    assert isinstance(provider, GeminiAPIProvider)


def test_explicit_claude_cli_with_cli_available_returns_claude_provider():
    env = {"LLM_PROVIDER": "claude_cli"}
    with patch.object(ClaudeCLIProvider, "is_available", return_value=True):
        provider = get_llm_provider(env=env)
    assert isinstance(provider, ClaudeCLIProvider)


def test_unspecified_provider_with_gemini_key_autoselects_gemini_api():
    env = {"GEMINI_API_KEY": "fake-key"}
    provider = get_llm_provider(env=env)
    assert isinstance(provider, GeminiAPIProvider)


def test_unspecified_provider_without_gemini_key_autoselects_claude_cli():
    env = {}
    with patch.object(ClaudeCLIProvider, "is_available", return_value=True):
        provider = get_llm_provider(env=env)
    assert isinstance(provider, ClaudeCLIProvider)


def test_invalid_llm_provider_value_raises_config_error():
    env = {"LLM_PROVIDER": "not_a_real_provider"}
    with pytest.raises(LLMConfigError):
        get_llm_provider(env=env)


def test_explicit_gemini_api_without_key_raises_config_error():
    env = {"LLM_PROVIDER": "gemini_api"}
    with pytest.raises(LLMConfigError):
        get_llm_provider(env=env)


def test_explicit_claude_cli_without_cli_installed_raises_config_error():
    env = {"LLM_PROVIDER": "claude_cli"}
    with patch.object(ClaudeCLIProvider, "is_available", return_value=False):
        with pytest.raises(LLMConfigError):
            get_llm_provider(env=env)


def test_gemini_key_takes_precedence_only_when_no_explicit_provider_set():
    # GEMINI_API_KEY가 있어도 LLM_PROVIDER=claude_cli가 명시되면 그걸 따라야 한다.
    env = {"LLM_PROVIDER": "claude_cli", "GEMINI_API_KEY": "fake-key"}
    with patch.object(ClaudeCLIProvider, "is_available", return_value=True):
        provider = get_llm_provider(env=env)
    assert isinstance(provider, ClaudeCLIProvider)


def test_llm_provider_value_is_case_insensitive_and_trimmed():
    env = {"LLM_PROVIDER": "  GEMINI_API  ", "GEMINI_API_KEY": "fake-key"}
    provider = get_llm_provider(env=env)
    assert isinstance(provider, GeminiAPIProvider)
