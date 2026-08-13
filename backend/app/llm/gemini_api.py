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
        use_vertex_ai: bool = True,
    ):
        if client is None and not api_key:
            raise GeminiAPIError("GEMINI_API_KEY가 설정되지 않았습니다.")
        self.model = model
        self.use_vertex_ai = use_vertex_ai  # introspectable for tests/debugging
        self._client = client or self._build_client(api_key, use_vertex_ai)

    @staticmethod
    def _build_client(api_key: str, use_vertex_ai: bool = True):
        try:
            from google import genai
        except ImportError as exc:
            raise GeminiAPIError(
                "google-genai 패키지가 설치되어 있지 않습니다. "
                "`pip install google-genai`로 설치하세요."
            ) from exc
        # 실키 테스트로 확인(2026-08-13): 이 프로젝트에서 발급된 API 키는 일반
        # Gemini Developer API(AI Studio) 키가 아니라 Vertex AI Express Mode
        # 키다(Cloud Console 자격증명 화면에 "vertex-express" 서비스 계정 바인딩,
        # 제한사항 "Agent Platform API"로 표시됨). 이런 키로 vertexai=False(기본
        # google-genai 동작, generativelanguage.googleapis.com 대상)를 쓰면
        # 403 PERMISSION_DENIED(API_KEY_SERVICE_BLOCKED)가 난다 -- 반드시
        # vertexai=True로 Vertex AI 엔드포인트를 타야 한다. GEMINI_USE_VERTEX_AI
        # 환경변수로 끌 수 있게 열어둔다(일반 AI Studio 키를 쓰게 되는 경우 대비).
        return genai.Client(api_key=api_key, vertexai=use_vertex_ai)

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
