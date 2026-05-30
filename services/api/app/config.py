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
    # Default to a file-backed SQLite DB under the api service so the CLI works without Docker.
    # Set DATABASE_URL=postgresql+psycopg://... when Postgres is up (locally or in Azure).
    database_url: str = Field(default="sqlite+pysqlite:///./webbwatch.db")
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
    # Phase 2: webhook endpoint stays off until we have a public URL registered
    # with AWS SNS. Verification is independently controllable so local dev can
    # POST canned payloads against it.
    jwst_sns_enable: bool = Field(default=False)
    jwst_sns_verify_signature: bool = Field(default=True)

    # ---- Phase 2: alerts ----
    discord_webhook_url: str | None = Field(default=None)

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

    # ---- Phase 5: local AI (Ollama, OpenAI-compatible endpoint) ----
    # Ollama is the user's responsibility to install + run. The worker pings it
    # per job and no-ops if unreachable; LOCAL_AI_ENABLE gates enqueue so dev
    # sessions without Ollama don't accumulate failure rows. The base URL ends
    # in /v1 because that's Ollama's OpenAI-compatible path (default targets a
    # no-Docker localhost install; the .env.example uses host.docker.internal).
    ollama_base_url: str = Field(default="http://localhost:11434/v1")
    local_ai_enable: bool = Field(default=False)
    local_ai_model: str = Field(default="llama3.1:8b-instruct-q4_K_M")
    # Phase 5.5: vision is opt-in + on-demand (a heavier multimodal model). On an
    # 8 GB GPU Ollama swaps between the text and vision models, so we don't
    # auto-run it. Default fits 8 GB; llama3.2-vision:11b is better on >=12 GB.
    local_ai_vision_enable: bool = Field(default=False)
    local_ai_vision_model: str = Field(default="llava:7b")
    local_ai_max_tokens: int = Field(default=1024)
    local_ai_temperature: float = Field(default=0.2)
    local_ai_request_timeout_seconds: int = Field(default=120)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
