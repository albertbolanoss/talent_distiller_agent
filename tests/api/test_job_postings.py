"""Tests for the job-posting-upload endpoint."""

from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import talent_distiller_agent.api.job_postings as job_postings_module
from talent_distiller_agent.api.job_postings import upload_job_posting
from talent_distiller_agent.settings import Settings


def _client(job_posting_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        job_postings_module,
        "get_settings",
        lambda: Settings(_env_file=None, job_posting_dir=str(job_posting_dir)),
    )
    app = Starlette(routes=[Route("/job_postings", upload_job_posting, methods=["POST"])])
    return TestClient(app)


def test_uploads_a_supported_file_into_the_job_posting_dir(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/job_postings", files={"file": ("job.pdf", b"%PDF-1.4", "application/pdf")}
    )

    assert response.status_code == 201
    assert response.json() == {"filename": "job.pdf", "size": len(b"%PDF-1.4")}
    assert (tmp_path / "job.pdf").read_bytes() == b"%PDF-1.4"


def test_creates_the_job_posting_dir_when_it_does_not_exist_yet(tmp_path, monkeypatch):
    missing_dir = tmp_path / "does-not-exist-yet"
    client = _client(missing_dir, monkeypatch)

    response = client.post("/job_postings", files={"file": ("job.md", b"# hi")})

    assert response.status_code == 201
    assert (missing_dir / "job.md").read_bytes() == b"# hi"


def test_adds_a_suffix_when_a_file_with_the_same_name_already_exists(tmp_path, monkeypatch):
    (tmp_path / "job.txt").write_text("old", encoding="utf-8")
    client = _client(tmp_path, monkeypatch)

    response = client.post("/job_postings", files={"file": ("job.txt", b"new")})

    assert response.status_code == 201
    filename = response.json()["filename"]
    assert filename != "job.txt"
    assert filename.startswith("job-") and filename.endswith(".txt")
    assert (tmp_path / filename).read_bytes() == b"new"
    assert (tmp_path / "job.txt").read_text(encoding="utf-8") == "old"


def test_sanitizes_path_traversal_attempts_in_the_filename(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post("/job_postings", files={"file": ("../../etc/job.txt", b"hi")})

    assert response.status_code == 201
    assert response.json()["filename"] == "job.txt"
    assert (tmp_path / "job.txt").read_bytes() == b"hi"
    assert not (tmp_path.parent / "etc").exists()


def test_rejects_a_missing_file_field(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post("/job_postings", data={})

    assert response.status_code == 400
    assert "file" in response.json()["error"].lower()
    assert list(tmp_path.iterdir()) == []


def test_rejects_a_file_field_that_is_not_an_uploaded_file(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post("/job_postings", data={"file": "not-a-file"})

    assert response.status_code == 400
    assert "file" in response.json()["error"].lower()


def test_rejects_an_unsupported_extension(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post("/job_postings", files={"file": ("job.exe", b"MZ")})

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "Unsupported file type '.exe'."
    assert body["supported_extensions"] == [".docx", ".markdown", ".md", ".pdf", ".txt"]
    assert not (tmp_path / "job.exe").exists()


def test_rejects_a_file_with_no_extension(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post("/job_postings", files={"file": ("job", b"hi")})

    assert response.status_code == 400
    assert response.json()["error"] == "Unsupported file type '(none)'."
