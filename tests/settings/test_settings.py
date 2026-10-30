"""Tests for the application settings' derived folder defaults."""

from candidate_match_agent_cli.settings import Settings


def test_resolves_default_folders_from_the_resume_and_job_posting_dirs():
    settings = Settings(_env_file=None, resume_dir="resume", job_posting_dir="job_posting")

    assert settings.coordinator_processed_folder == "resume/processed"
    assert settings.coordinator_failed_folder == "resume/failed"
    assert settings.job_posting_processed_folder == "job_posting/processed"
    assert settings.job_posting_failed_folder == "job_posting/failed"


def test_keeps_explicitly_provided_folders_instead_of_the_derived_defaults():
    settings = Settings(
        _env_file=None,
        resume_dir="resume",
        job_posting_dir="job_posting",
        coordinator_processed_folder="custom/resume-processed",
        coordinator_failed_folder="custom/resume-failed",
        job_posting_processed_folder="custom/job-posting-processed",
        job_posting_failed_folder="custom/job-posting-failed",
    )

    assert settings.coordinator_processed_folder == "custom/resume-processed"
    assert settings.coordinator_failed_folder == "custom/resume-failed"
    assert settings.job_posting_processed_folder == "custom/job-posting-processed"
    assert settings.job_posting_failed_folder == "custom/job-posting-failed"
