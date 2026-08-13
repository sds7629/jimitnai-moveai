"""app.llm.claude_cli.ClaudeCLIProvider에 대한 테스트.

subprocess.run과 shutil.which를 모킹해서 실제 로컬에 claude CLI가
설치되어 있는지 여부와 무관하게 동작을 검증한다.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.llm.claude_cli import ClaudeCLIError, ClaudeCLIProvider


def _fake_completed_process(stdout="", stderr="", returncode=0):
    return MagicMock(stdout=stdout, stderr=stderr, returncode=returncode)


def test_generate_returns_stdout_on_success():
    provider = ClaudeCLIProvider()
    with patch("app.llm.claude_cli.shutil.which", return_value="/usr/local/bin/claude"), patch(
        "app.llm.claude_cli.subprocess.run",
        return_value=_fake_completed_process(stdout="hello world\n"),
    ) as mock_run:
        result = provider.generate("hi")

    assert result == "hello world"
    mock_run.assert_called_once()


def test_generate_raises_when_cli_not_installed():
    provider = ClaudeCLIProvider()
    with patch("app.llm.claude_cli.shutil.which", return_value=None):
        with pytest.raises(ClaudeCLIError):
            provider.generate("hi")


def test_generate_raises_on_nonzero_exit_code_and_includes_stderr():
    provider = ClaudeCLIProvider()
    with patch("app.llm.claude_cli.shutil.which", return_value="/usr/local/bin/claude"), patch(
        "app.llm.claude_cli.subprocess.run",
        return_value=_fake_completed_process(stderr="boom", returncode=1),
    ):
        with pytest.raises(ClaudeCLIError, match="boom"):
            provider.generate("hi")


def test_generate_raises_on_timeout():
    provider = ClaudeCLIProvider(timeout=5)
    with patch("app.llm.claude_cli.shutil.which", return_value="/usr/local/bin/claude"), patch(
        "app.llm.claude_cli.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=5),
    ):
        with pytest.raises(ClaudeCLIError):
            provider.generate("hi")


def test_system_prompt_is_included_in_command():
    provider = ClaudeCLIProvider()
    with patch("app.llm.claude_cli.shutil.which", return_value="/usr/local/bin/claude"), patch(
        "app.llm.claude_cli.subprocess.run",
        return_value=_fake_completed_process(stdout="ok"),
    ) as mock_run:
        provider.generate("hi", system="you are a helpful assistant")

    called_command = mock_run.call_args.args[0]
    assert "--append-system-prompt" in called_command
    assert "you are a helpful assistant" in called_command
    assert called_command[:3] == ["claude", "-p", "hi"]


def test_generate_without_system_omits_append_system_prompt_flag():
    provider = ClaudeCLIProvider()
    with patch("app.llm.claude_cli.shutil.which", return_value="/usr/local/bin/claude"), patch(
        "app.llm.claude_cli.subprocess.run",
        return_value=_fake_completed_process(stdout="ok"),
    ) as mock_run:
        provider.generate("hi")

    called_command = mock_run.call_args.args[0]
    assert "--append-system-prompt" not in called_command


def test_custom_cli_path_is_used_in_command():
    provider = ClaudeCLIProvider(cli_path="/opt/bin/claude")
    with patch("app.llm.claude_cli.shutil.which", return_value="/opt/bin/claude"), patch(
        "app.llm.claude_cli.subprocess.run",
        return_value=_fake_completed_process(stdout="ok"),
    ) as mock_run:
        provider.generate("hi")

    called_command = mock_run.call_args.args[0]
    assert called_command[0] == "/opt/bin/claude"
