import pytest

from tests.conftest import UnsafeTestEnvironmentError, ensure_safe_test_environment


def test_ensure_safe_test_environment_raises_when_var_missing():
    with pytest.raises(UnsafeTestEnvironmentError):
        ensure_safe_test_environment({})


def test_ensure_safe_test_environment_raises_when_var_explicitly_off():
    with pytest.raises(UnsafeTestEnvironmentError):
        ensure_safe_test_environment({"RUN_INTEGRATION_TESTS": "0"})


def test_ensure_safe_test_environment_raises_when_var_not_exactly_one():
    with pytest.raises(UnsafeTestEnvironmentError):
        ensure_safe_test_environment({"RUN_INTEGRATION_TESTS": "true"})


def test_ensure_safe_test_environment_passes_when_var_set():
    ensure_safe_test_environment({"RUN_INTEGRATION_TESTS": "1"})
