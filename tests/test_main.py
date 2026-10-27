"""Tests for the resume-polling entrypoint."""

from pathlib import Path

import pytest

import candidate_match_agent.main as main_module
from candidate_match_agent.libs.settings import Settings


class _StopLoop(Exception):
    """Raised by the fake `asyncio.sleep` to break process_resumes()'s infinite loop in tests."""


def _settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "resume_dir": str(tmp_path),
        "resume_poll_interval_seconds": 42,
        "resume_max_files_per_batch": 10,
    }
    return Settings(_env_file=None, **{**defaults, **overrides})


def _make_resume_files(tmp_path: Path) -> None:
    (tmp_path / "c.txt").write_text("c", encoding="utf-8")
    (tmp_path / "a.pdf").write_bytes(b"a")
    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    (tmp_path / "ignored.csv").write_text("not a resume", encoding="utf-8")
    (tmp_path / "subdir").mkdir()


async def test_processes_every_supported_file_in_sorted_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _make_resume_files(tmp_path)
    processed: list[str] = []

    async def fake_run_coordinator(model: str, resume_path: str) -> None:
        assert model == main_module.MODEL
        processed.append(resume_path)

    async def fake_sleep(_seconds: float) -> None:
        raise _StopLoop

    monkeypatch.setattr(main_module, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(main_module, "run_coordinator", fake_run_coordinator)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(_StopLoop):
        await main_module.process_resumes()

    assert [Path(p).name for p in processed] == ["a.pdf", "b.md", "c.txt"]


async def test_limits_each_batch_to_resume_max_files_per_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _make_resume_files(tmp_path)
    processed: list[str] = []

    async def fake_run_coordinator(_model: str, resume_path: str) -> None:
        processed.append(resume_path)

    async def fake_sleep(_seconds: float) -> None:
        raise _StopLoop

    monkeypatch.setattr(
        main_module, "get_settings", lambda: _settings(tmp_path, resume_max_files_per_batch=2)
    )
    monkeypatch.setattr(main_module, "run_coordinator", fake_run_coordinator)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(_StopLoop):
        await main_module.process_resumes()

    assert len(processed) == 2


async def test_sleeps_for_the_configured_poll_interval_between_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    sleep_calls: list[float] = []

    async def fake_run_coordinator(*_args) -> None:
        return None

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        raise _StopLoop

    monkeypatch.setattr(
        main_module, "get_settings", lambda: _settings(tmp_path, resume_poll_interval_seconds=7)
    )
    monkeypatch.setattr(main_module, "run_coordinator", fake_run_coordinator)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(_StopLoop):
        await main_module.process_resumes()

    assert sleep_calls == [7]


def test_main_runs_process_resumes(monkeypatch: pytest.MonkeyPatch):
    calls = []

    async def fake_process_resumes() -> None:
        calls.append(True)

    monkeypatch.setattr(main_module, "process_resumes", fake_process_resumes)

    main_module.main()

    assert calls == [True]
