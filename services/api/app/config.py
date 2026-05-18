from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

AIProvider = Literal["openai", "azure_openai"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- App ----
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # ---- API ----
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_public_url: str = Field(default="http://localhost:8000")
    cors_allowed_origins: str = Field(default="http://localhost:3000")

    # ---- Database / Redis ----
    database_url: str = Field(
        default="postgresql+psycopg://webbwatch:webbwatch_dev_password@localhost:5432/webbwatch"
    )
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ---- Azure Blob Storage (our storage; Azurite locally) ----
    # In local dev: connection string against Azurite (devstoreaccount1).
    # In prod on Container Apps: leave the connection string empty and set
    # AZURE_STORAGE_ACCOUNT_URL so DefaultAzureCredential picks up managed identity.
    azure_storage_connection_string: str | None = Field(default=None)
    azure_storage_account_url: str | None = Field(default=None)
    azure_blob_container_fits: str = Field(default="webbwatch-fits")
    azure_blob_container_previews: str = Field(default="webbwatch-previews")

    # ---- JWST source (AWS public bucket, anonymous) ----
    jwst_s3_bucket: str = Field(default="stpubdata")
    jwst_s3_prefix: str = Field(default="jwst/")
    jwst_s3_region: str = Field(default="us-east-1")
    jwst_sns_topic_arn: str = Field(
        default="arn:aws:sns:us-east-1:879230861493:stpubdata/jwst"
    )
    jwst_sns_webhook_url: str | None = Field(default=None)

    # ---- Cloud AI provider ----
    ai_provider: AIProvider = Field(default="openai")

    # OpenAI direct
    openai_api_key: str | None = Field(default=None)
    openai_model: str = Field(default="gpt-4.1-mini")

    # Azure OpenAI
    azure_openai_endpoint: str | None = Field(default=None)
    azure_openai_api_key: str | None = Field(default=None)
    azure_openai_api_version: str = Field(default="2025-01-01-preview")
    azure_openai_deployment_chat: str = Field(default="gpt-4.1-mini")
    azure_openai_deployment_vision: str = Field(default="gpt-4.1-mini")
    azure_openai_use_managed_identity: bool = Field(default=False)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
