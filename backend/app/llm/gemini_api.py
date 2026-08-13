from typing import Optional

from .provider import LLMProvider

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiAPIError(RuntimeError):
    """Gemini API 호출 중 발생한 오류."""


class GeminiAPIProvider(LLMProvider):
    """Gemini API(google-genai SDK)를 호출하는 프로바이더."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        client=None,
    ):
        if client is None and not api_key:
            raise GeminiAPIError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self.model = model
        self._client = client or self._build_client(api_key)

    @staticmethod
    def _build_client(api_key: str):
        try:
            from google import genai
        except ImportError as exc:
            raise GeminiAPIError(
                "google-genai 패키지가 설치되어 있지 않습니다. "
                "`pip install google-genai`로 설치하세요."
            ) from exc
        return genai.Client(api_key=api_key)

    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        config = {"temperature": temperature}
        if system:
            config["system_instruction"] = system

        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
        except Exception as exc:  # SDK별 예외 타입이 다양하므로 포괄적으로 래핑한다
            raise GeminiAPIError(f"Gemini API 호출 실패: {exc}") from exc

        text = getattr(response, "text", None)
        if not text:
            raise GeminiAPIError("Gemini API 응답에 text가 없습니다.")
        return text
