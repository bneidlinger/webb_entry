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


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
