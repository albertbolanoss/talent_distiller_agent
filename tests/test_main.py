"""Tests for the resume-polling entrypoint."""

from pathlib import Path

import pytest

import candidate_match_agent_cli.main as main_module
from candidate_match_agent_cli.settings import Settings


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


async def test_processes_every_supported_file_in_creation_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _make_resume_files(tmp_path)
    processed: list[str] = []
    creation_times = {"b.md": 1, "c.txt": 2, "a.pdf": 3}

    async def fake_run_coordinator(resume_path: str) -> None:
        processed.append(resume_path)

    async def fake_sleep(_seconds: float) -> None:
        raise _StopLoop

    monkeypatch.setattr(main_module, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(main_module, "run_coordinator", fake_run_coordinator)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main_module, "get_creation_time", lambda path: creation_times[path.name])

    with pytest.raises(_StopLoop):
        await main_module.start_process()

    assert [Path(p).name for p in processed] == ["b.md", "c.txt", "a.pdf"]


async def test_limits_each_batch_to_resume_max_files_per_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _make_resume_files(tmp_path)
    processed: list[str] = []

    async def fake_run_coordinator(resume_path: str) -> None:
        processed.append(resume_path)

    async def fake_sleep(_seconds: float) -> None:
        raise _StopLoop

    monkeypatch.setattr(
        main_module, "get_settings", lambda: _settings(tmp_path, resume_max_files_per_batch=2)
    )
    monkeypatch.setattr(main_module, "run_coordinator", fake_run_coordinator)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(_StopLoop):
        await main_module.start_process()

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
        await main_module.start_process()

    assert sleep_calls == [7]


def test_get_creation_time_falls_back_to_mtime_when_birthtime_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    file_path = tmp_path / "resume.txt"
    file_path.write_text("x", encoding="utf-8")

    class _StatWithoutBirthtime:
        st_mtime = 123.0

    monkeypatch.setattr(Path, "stat", lambda self: _StatWithoutBirthtime())

    assert main_module.get_creation_time(file_path) == 123.0


async def test_logs_and_continues_when_a_coordinator_run_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    (tmp_path / "a.pdf").write_bytes(b"a")

    async def failing_run_coordinator(resume_path: str) -> None:
        raise RuntimeError("boom")

    async def fake_sleep(_seconds: float) -> None:
        raise _StopLoop

    monkeypatch.setattr(main_module, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(main_module, "run_coordinator", failing_run_coordinator)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    with caplog.at_level("ERROR"):
        with pytest.raises(_StopLoop):
            await main_module.start_process()

    assert "Failed to process" in caplog.text


async def test_logs_and_continues_when_a_poll_loop_iteration_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    missing_dir = tmp_path / "does-not-exist"

    async def fake_sleep(_seconds: float) -> None:
        raise _StopLoop

    monkeypatch.setattr(main_module, "get_settings", lambda: _settings(missing_dir))
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    with caplog.at_level("ERROR"):
        with pytest.raises(_StopLoop):
            await main_module.start_process()

    assert "Poll loop iteration failed" in caplog.text
