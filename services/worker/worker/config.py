from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    redis_url: str = Field(default="redis://localhost:6379/0")
    database_url: str = Field(
        default="postgresql+psycopg://webbwatch:webbwatch_dev_password@localhost:5432/webbwatch"
    )

    queue_names: list[str] = Field(default_factory=lambda: ["default", "ingest", "analyze"])

    # MAST polling — Phase 2 (project-phase2-decisions.md).
    # Defaults to four primary instruments; override with MAST_POLL_INSTRUMENTS=NIRCAM,MIRI.
    mast_poll_instruments: list[str] = Field(
        default_factory=lambda: ["NIRCAM", "MIRI", "NIRSPEC", "NIRISS"]
    )
    mast_poll_limit: int = Field(default=100)
    mast_poll_interval_seconds: int = Field(default=30 * 60)

    # S3 listing — anonymous (botocore.UNSIGNED), 6h cadence.
    jwst_s3_bucket: str = Field(default="stpubdata")
    jwst_s3_prefix: str = Field(default="jwst/")
    jwst_s3_region: str = Field(default="us-east-1")
    s3_poll_interval_seconds: int = Field(default=6 * 60 * 60)
    s3_poll_max_keys: int = Field(default=1000)


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
