"""Tests for the application settings' derived folder defaults."""

from talent_distiller_agent.settings import Settings


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


def test_redis_settings_default_when_no_env_file():
    settings = Settings(_env_file=None)

    assert settings.redis_host == "localhost"
    assert settings.redis_password.get_secret_value() == ""
    assert settings.redis_db == 0


def test_observability_settings_default_when_no_env_file():
    settings = Settings(_env_file=None)

    assert settings.observability_enabled is True
    assert settings.prompt_log_dir == "documentation/prompt_log"
    assert settings.agent_transcript_dir == "documentation/agent_transcript"
