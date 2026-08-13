from abc import ABC, abstractmethod
from typing import Optional


class LLMProvider(ABC):
    """모든 LLM 백엔드가 구현해야 하는 공통 인터페이스."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        """prompt에 대한 LLM 응답 텍스트를 반환한다."""
        raise NotImplementedError
