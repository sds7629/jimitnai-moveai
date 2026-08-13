"""Gemini Embedding API 클라이언트 (agents/knowledge-retrieval.md).

`app/llm/gemini_api.py`의 `GeminiAPIProvider`는 텍스트 생성(`generate_content`)만
지원하고 임베딩은 지원하지 않는다. 이 모듈이 그 빈자리를 채운다.

인증 체계는 새로 만들지 않는다 — `app.core.config.settings.gemini_api_key`
(=`GEMINI_API_KEY` 환경변수)를 그대로 재사용하고, 에러도 `gemini_api`의
`GeminiAPIError`를 그대로 감싸 던진다. google-genai SDK 호출 실패/미설치/
API 키 부재를 모두 이 하나의 예외 타입으로 처리하면, 호출부(검색 함수·시드
스크립트)가 예외 타입 하나만 신경 쓰면 되게 만드는 목적이다.
"""

from __future__ import annotations

from typing import Optional

from .gemini_api import GeminiAPIError

DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"

# document_chunks.embedding은 vector(768)로 고정되어 있다 (db/init/002-schema.sql,
# app/models/document.py의 EMBEDDING_DIM 참고). 이 상수도 그 고정값과 반드시
# 일치해야 하며, 다른 차원의 임베딩 모델로 바꾸려면 스키마/컬럼도 함께
# 바꿔야 한다.
#
# 실제 API로 확인한 내용(실키로 첫 테스트, 2026-08-13): 이전에 쓰던
# "text-embedding-004"는 이 API 버전/계정에서 404로 존재하지 않는다 --
# `client.models.list()`로 embedContent를 지원하는 모델을 조회하면
# gemini-embedding-001 계열만 나온다. 이 모델은 기본 출력 차원이 768보다 커서
# (Matryoshka 표현학습 지원 모델), embed_content 호출 시
# config={"output_dimensionality": EMBEDDING_DIM}을 명시적으로 넘겨 768차원으로
# 맞춘다 -- 혹시 이 옵션이 무시되거나 SDK/모델이 바뀌어도, 아래 차원 검증이
# 스키마 불일치를 조용히 넘기지 않고 곧바로 GeminiAPIError로 걸러낸다.
EMBEDDING_DIM = 768


def _build_client(api_key: str, use_vertex_ai: bool = True):
    try:
        from google import genai
    except ImportError as exc:
        raise GeminiAPIError(
            "google-genai 패키지가 설치되어 있지 않습니다. "
            "`pip install google-genai`로 설치하세요."
        ) from exc
    # app/llm/gemini_api.py의 GeminiAPIProvider._build_client와 동일한 이유로
    # vertexai=True가 기본값이다 -- 이 프로젝트의 실제 키는 Vertex AI Express
    # Mode 키라 vertexai=False로는 403 PERMISSION_DENIED(API_KEY_SERVICE_BLOCKED)가 난다.
    return genai.Client(api_key=api_key, vertexai=use_vertex_ai)


def embed_text(
    text: str,
    *,
    api_key: Optional[str] = None,
    model: str = DEFAULT_EMBEDDING_MODEL,
    client=None,
    use_vertex_ai: Optional[bool] = None,
) -> list[float]:
    """텍스트 한 건을 Gemini Embedding API로 768차원 벡터로 변환한다.

    인증 우선순위: 명시적으로 넘긴 `client` > 명시적으로 넘긴 `api_key` >
    `app.core.config.settings.gemini_api_key`. 셋 다 없으면(즉 실제
    GEMINI_API_KEY가 설정돼 있지 않으면) 네트워크를 시도하지 않고 곧바로
    `GeminiAPIError`를 던진다 — 시드 스크립트가 이 메시지를 그대로 사용자에게
    노출해 "키를 설정하라"는 안내를 준다.

    테스트에서는 `client=<fake>`를 주입해 실제 SDK/네트워크 없이 검증한다
    (`app/llm/gemini_api.py` 테스트와 동일한 패턴).
    """
    if not text or not text.strip():
        raise GeminiAPIError("임베딩할 텍스트가 비어 있습니다.")

    if client is None:
        from app.core.config import settings

        resolved_key = api_key or settings.gemini_api_key
        if not resolved_key:
            raise GeminiAPIError(
                "GEMINI_API_KEY가 설정되지 않았습니다. 임베딩을 생성하려면 "
                "환경변수 GEMINI_API_KEY(.env 또는 docker-compose 환경변수)를 "
                "설정한 뒤 다시 실행하세요."
            )
        resolved_use_vertex_ai = (
            use_vertex_ai if use_vertex_ai is not None else settings.gemini_use_vertex_ai
        )
        client = _build_client(resolved_key, resolved_use_vertex_ai)

    try:
        response = client.models.embed_content(
            model=model,
            contents=text,
            config={"output_dimensionality": EMBEDDING_DIM},
        )
    except Exception as exc:  # SDK별 예외 타입이 다양하므로 포괄적으로 래핑한다
        raise GeminiAPIError(f"Gemini Embedding API 호출 실패: {exc}") from exc

    embeddings = getattr(response, "embeddings", None)
    if not embeddings or getattr(embeddings[0], "values", None) is None:
        raise GeminiAPIError("Gemini Embedding API 응답에 embedding 값이 없습니다.")

    values = list(embeddings[0].values)
    if len(values) != EMBEDDING_DIM:
        raise GeminiAPIError(
            f"임베딩 차원이 예상과 다릅니다 (기대: {EMBEDDING_DIM}, 실제: {len(values)}). "
            "document_chunks.embedding 컬럼은 vector(768)로 고정되어 있어 다른 "
            "차원의 임베딩 모델을 쓸 수 없습니다."
        )
    return values
