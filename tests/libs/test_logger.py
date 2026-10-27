import logging
import sys

import pytest

import candidate_match_agent.libs.logger as logger_module
from candidate_match_agent.libs.logger import get_logger


@pytest.fixture(autouse=True)
def _reset_root_logger(monkeypatch: pytest.MonkeyPatch):
    """Undo _configure()'s module-level memoization and handlers between tests.

    Resetting `propagate` matters too: once a test sets it to False, pytest's
    own log-capturing attaches its handlers directly to this logger on every
    later test (it does that for any logger that won't propagate to root),
    which would otherwise pollute `root.handlers` for unrelated tests.
    """
    monkeypatch.setattr(logger_module, "_configured", False)
    root = logging.getLogger(logger_module._ROOT_LOGGER_NAME)
    root.handlers.clear()
    root.propagate = True
    yield
    root.handlers.clear()
    root.propagate = True


def test_returns_a_logger_with_the_requested_name():
    logger = get_logger("some.module")

    assert isinstance(logger, logging.Logger)
    assert logger.name == "some.module"


def test_first_call_attaches_a_single_stderr_handler_to_the_root_logger():
    get_logger("some.module")

    root = logging.getLogger(logger_module._ROOT_LOGGER_NAME)
    assert len(root.handlers) == 1
    handler = root.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stderr
    assert root.propagate is False


def test_root_logger_level_comes_from_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CANDIDATE_MATCH_AGENT_LOG_LEVEL", "WARNING")

    get_logger("some.module")

    root = logging.getLogger(logger_module._ROOT_LOGGER_NAME)
    assert root.level == logging.WARNING


def test_calling_get_logger_again_does_not_add_a_second_handler():
    get_logger("some.module")
    get_logger("some.other.module")

    root = logging.getLogger(logger_module._ROOT_LOGGER_NAME)
    assert len(root.handlers) == 1


def test_calling_get_logger_again_does_not_recompute_the_level(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CANDIDATE_MATCH_AGENT_LOG_LEVEL", "WARNING")
    get_logger("some.module")

    root = logging.getLogger(logger_module._ROOT_LOGGER_NAME)
    root.setLevel(logging.CRITICAL)  # simulate something else changing it after configure

    monkeypatch.setenv("CANDIDATE_MATCH_AGENT_LOG_LEVEL", "DEBUG")
    get_logger("some.other.module")

    assert root.level == logging.CRITICAL
