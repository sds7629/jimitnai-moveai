import os
from typing import Mapping, Optional

from dotenv import load_dotenv

from .claude_cli import ClaudeCLIProvider
from .gemini_api import GeminiAPIProvider
from .provider import LLMProvider

VALID_PROVIDERS = {"gemini_api", "claude_cli"}
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_CLAUDE_CLI_PATH = "claude"
DEFAULT_CLAUDE_CLI_TIMEOUT = 120


class LLMConfigError(RuntimeError):
    """LLM 프로바이더 설정 오류."""


def get_llm_provider(env: Optional[Mapping[str, str]] = None) -> LLMProvider:
    """.env 설정을 기준으로 사용할 LLM 프로바이더를 결정한다.

    우선순위:
    1. LLM_PROVIDER가 명시되어 있으면 그 값을 그대로 사용한다 (유효하지 않으면 에러).
    2. 명시되어 있지 않으면 GEMINI_API_KEY 존재 여부로 자동 결정한다
       (있으면 gemini_api, 없으면 claude_cli).

    env를 넘기지 않으면 실제 `.env` 파일을 로드해 os.environ 기준으로 판단한다.
    테스트에서는 env에 dict를 넘겨 실제 환경변수/`.env` 파일에 영향을 주지 않을 수 있다.
    """
    if env is None:
        load_dotenv()
        source = os.environ
    else:
        source = env

    explicit = (source.get("LLM_PROVIDER") or "").strip().lower()
    gemini_key = (source.get("GEMINI_API_KEY") or "").strip()

    if explicit:
        if explicit not in VALID_PROVIDERS:
            raise LLMConfigError(
                f"LLM_PROVIDER='{explicit}'는 지원하지 않는 값입니다. "
                f"{sorted(VALID_PROVIDERS)} 중 하나여야 합니다."
            )
        provider_name = explicit
    else:
        provider_name = "gemini_api" if gemini_key else "claude_cli"

    if provider_name == "gemini_api":
        if not gemini_key:
            raise LLMConfigError(
                "LLM_PROVIDER=gemini_api로 지정(혹은 자동 선택)되었지만 "
                "GEMINI_API_KEY가 비어 있습니다."
            )
        model = (source.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip()
        return GeminiAPIProvider(api_key=gemini_key, model=model)

    cli_path = (source.get("CLAUDE_CLI_PATH") or DEFAULT_CLAUDE_CLI_PATH).strip()
    timeout = int(source.get("CLAUDE_CLI_TIMEOUT") or DEFAULT_CLAUDE_CLI_TIMEOUT)
    provider = ClaudeCLIProvider(cli_path=cli_path or DEFAULT_CLAUDE_CLI_PATH, timeout=timeout)
    if not provider.is_available():
        raise LLMConfigError(
            f"LLM_PROVIDER=claude_cli로 지정(혹은 자동 선택)되었지만 "
            f"'{cli_path}' 실행 파일을 PATH에서 찾을 수 없습니다."
        )
    return provider
