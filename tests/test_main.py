"""Tests for the resume and job-posting polling entrypoints."""

from pathlib import Path

import pytest

import candidate_match_agent_cli.main as main_module
from candidate_match_agent_cli.settings import Settings
from candidate_match_agent_cli.storage import DocumentType


class _StopLoop(Exception):
    """Raised by the fake `asyncio.sleep` to break a poll loop's infinite loop in tests."""


def _settings(tmp_path: Path, **overrides) -> Settings:
    defaults = {
        "resume_dir": str(tmp_path / "resume"),
        "resume_poll_interval_seconds": 42,
        "resume_max_files_per_batch": 10,
        "job_posting_dir": str(tmp_path / "job_posting"),
        "job_posting_poll_interval_seconds": 43,
        "job_posting_max_files_per_batch": 10,
    }
    return Settings(_env_file=None, **{**defaults, **overrides})


def _make_document_files(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "c.txt").write_text("c", encoding="utf-8")
    (directory / "a.pdf").write_bytes(b"a")
    (directory / "b.md").write_text("b", encoding="utf-8")
    (directory / "ignored.csv").write_text("not a document", encoding="utf-8")
    (directory / "subdir").mkdir()


async def test_process_only_resumes_processes_every_supported_file_in_creation_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    resume_dir = tmp_path / "resume"
    _make_document_files(resume_dir)
    processed: list[tuple[str, DocumentType]] = []
    creation_times = {"b.md": 1, "c.txt": 2, "a.pdf": 3}

    async def fake_run_coordinator(resume_path: str, doc_type: DocumentType) -> None:
        processed.append((resume_path, doc_type))

    async def fake_sleep(_seconds: float) -> None:
        raise _StopLoop

    monkeypatch.setattr(main_module, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(main_module, "run_coordinator", fake_run_coordinator)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main_module, "get_creation_time", lambda path: creation_times[path.name])

    with pytest.raises(_StopLoop):
        await main_module.process_only_resumes()

    assert [Path(p).name for p, _ in processed] == ["b.md", "c.txt", "a.pdf"]
    assert {doc_type for _, doc_type in processed} == {DocumentType.RESUME}


async def test_process_job_postings_processes_files_tagged_as_job_postings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    job_posting_dir = tmp_path / "job_posting"
    _make_document_files(job_posting_dir)
    processed: list[tuple[str, DocumentType]] = []

    async def fake_run_coordinator(resume_path: str, doc_type: DocumentType) -> None:
        processed.append((resume_path, doc_type))

    async def fake_sleep(_seconds: float) -> None:
        raise _StopLoop

    monkeypatch.setattr(main_module, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(main_module, "run_coordinator", fake_run_coordinator)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(_StopLoop):
        await main_module.process_job_postings()

    assert len(processed) == 3
    assert {doc_type for _, doc_type in processed} == {DocumentType.JOB_POSTING}


async def test_limits_each_batch_to_the_configured_max_files_per_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    resume_dir = tmp_path / "resume"
    _make_document_files(resume_dir)
    processed: list[str] = []

    async def fake_run_coordinator(resume_path: str, doc_type: DocumentType) -> None:
        processed.append(resume_path)

    async def fake_sleep(_seconds: float) -> None:
        raise _StopLoop

    monkeypatch.setattr(
        main_module, "get_settings", lambda: _settings(tmp_path, resume_max_files_per_batch=2)
    )
    monkeypatch.setattr(main_module, "run_coordinator", fake_run_coordinator)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(_StopLoop):
        await main_module.process_only_resumes()

    assert len(processed) == 2


async def test_poll_loop_returns_without_processing_when_the_directory_has_no_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    resume_dir = tmp_path / "resume"
    calls: list[str] = []

    async def fake_run_coordinator(resume_path: str, doc_type: DocumentType) -> None:
        calls.append(resume_path)

    async def fake_sleep(_seconds: float) -> None:
        raise _StopLoop

    monkeypatch.setattr(main_module, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(main_module, "run_coordinator", fake_run_coordinator)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(_StopLoop):
        await main_module.process_only_resumes()

    assert calls == []
    assert resume_dir.exists()


async def test_process_directory_batch_returns_when_the_directory_does_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list[str] = []

    async def fake_run_coordinator(resume_path: str, doc_type: DocumentType) -> None:
        calls.append(resume_path)

    monkeypatch.setattr(main_module, "run_coordinator", fake_run_coordinator)

    await main_module._process_directory_batch(
        directory=tmp_path / "does-not-exist",
        doc_type=DocumentType.RESUME,
        max_files_per_batch=10,
    )

    assert calls == []


async def test_sleeps_for_the_configured_poll_interval_between_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    sleep_calls: list[float] = []

    async def fake_run_coordinator(*_args, **_kwargs) -> None:
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
        await main_module.process_only_resumes()

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
    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    (resume_dir / "a.pdf").write_bytes(b"a")

    async def failing_run_coordinator(resume_path: str, doc_type: DocumentType) -> None:
        raise RuntimeError("boom")

    async def fake_sleep(_seconds: float) -> None:
        raise _StopLoop

    monkeypatch.setattr(main_module, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(main_module, "run_coordinator", failing_run_coordinator)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    with caplog.at_level("ERROR"):
        with pytest.raises(_StopLoop):
            await main_module.process_only_resumes()

    assert "Failed to process" in caplog.text


async def test_logs_and_continues_when_a_poll_loop_iteration_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    async def fake_sleep(_seconds: float) -> None:
        raise _StopLoop

    async def failing_process_directory_batch(**_kwargs) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "get_settings", lambda: _settings(tmp_path))
    monkeypatch.setattr(main_module, "_process_directory_batch", failing_process_directory_batch)
    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    with caplog.at_level("ERROR"):
        with pytest.raises(_StopLoop):
            await main_module.process_only_resumes()

    assert "Poll loop iteration failed" in caplog.text


async def test_start_process_runs_the_resume_and_job_posting_pollers_concurrently(
    monkeypatch: pytest.MonkeyPatch,
):
    started: list[str] = []

    async def fake_process_only_resumes() -> None:
        started.append("resume")

    async def fake_process_job_postings() -> None:
        started.append("job_posting")

    monkeypatch.setattr(main_module, "process_only_resumes", fake_process_only_resumes)
    monkeypatch.setattr(main_module, "process_job_postings", fake_process_job_postings)

    await main_module.start_process()

    assert set(started) == {"resume", "job_posting"}
