import shutil
import subprocess
from typing import Optional

from .provider import LLMProvider


class ClaudeCLIError(RuntimeError):
    """로컬 claude CLI 실행 중 발생한 오류."""


class ClaudeCLIProvider(LLMProvider):
    """로컬에 설치된 `claude -p` (print mode) CLI를 호출하는 프로바이더."""

    def __init__(self, cli_path: str = "claude", timeout: int = 120):
        self.cli_path = cli_path
        self.timeout = timeout

    def is_available(self) -> bool:
        return shutil.which(self.cli_path) is not None

    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        if not self.is_available():
            raise ClaudeCLIError(
                f"'{self.cli_path}' 실행 파일을 PATH에서 찾을 수 없습니다. "
                "claude CLI가 설치·로그인되어 있는지 확인하세요."
            )

        command = [self.cli_path, "-p", prompt]
        if system:
            command += ["--append-system-prompt", system]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise ClaudeCLIError(
                f"claude CLI 호출이 {self.timeout}초 내에 끝나지 않았습니다."
            ) from exc

        if result.returncode != 0:
            raise ClaudeCLIError(
                f"claude CLI가 오류를 반환했습니다 (exit code {result.returncode}): "
                f"{result.stderr.strip()}"
            )

        return result.stdout.strip()
