from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")
    runtime_mode: Literal["local", "emulator", "cloud"] = "local"
    enable_cloud: bool = False  # Explicit human-authorized opt-in; never auto-detect ADC.
    ai_mode: Literal["mock", "real"] = "mock"
    ai_provider: Literal["vertex", "developer"] = "vertex"
    provider_image: Literal["vertex", "developer"] = "vertex"
    provider_read: Literal["vertex", "developer"] = "vertex"
    provider_conclude: Literal["vertex", "developer"] = "vertex"
    provider_embed: Literal["vertex", "developer"] = "vertex"
    vertex_location: str = "global"
    gemini_api_key: str | None = Field(default=None, repr=False)
    mock_delay_s: float = Field(default=0, ge=0)
    storage_mode: Literal["local", "gcs"] = "local"
    local_storage_dir: str = ".local_storage"
    model_image: str = "gemini-3.1-flash-image"
    model_read: str = "gemini-3.5-flash"
    model_conclude: str = "gemini-3.5-flash"
    model_embed: str = "gemini-embedding-001"
    ai_timeout_s: int = Field(default=60, ge=1)
    max_attempts: int = 3
    video_max_bytes: int = Field(default=10_000_000, ge=1)
    allowed_video_types: list[str] = ["video/webm", "video/mp4"]
    asset_ttl_hours: int = 24
    deadline_grace_s: int = Field(default=5, ge=0)
    heartbeat_interval_s: int = Field(default=5, ge=1)
    dropout_after_s: int = Field(default=15, ge=1)
    text_max_length: int = Field(default=2000, ge=1)
    json_max_bytes: int = Field(default=1_000_000, ge=1024)
    gesture_batch_max_bytes: int = Field(default=250_000, ge=1024, le=250_000)
    project_id: str = Field(
        default="demo-gesture-relay",
        validation_alias=AliasChoices("project_id", "PROJECT_ID", "gcp_project", "GCP_PROJECT"),
    )
    bucket_name: str = Field(
        default="",
        validation_alias=AliasChoices(
            "bucket_name", "BUCKET_NAME", "storage_bucket", "STORAGE_BUCKET"
        ),
    )
    tasks_location: str = ""
    tasks_queue: str = ""
    worker_url: str = ""
    deadline_url: str = ""
    tasks_service_account: str = ""
    internal_audience: str = ""
    cors_origins: list[str] = []
    join_attempt_limit: int = 10
    join_attempt_window_s: int = 60
    room_create_uid_limit: int = Field(default=10, ge=1)
    round_start_uid_limit: int = Field(default=3, ge=1)
    room_create_global_limit: int = Field(default=0, ge=0)
    round_start_global_limit: int = Field(default=0, ge=0)

    @property
    def gcp_project(self) -> str:
        return self.project_id

    @property
    def storage_bucket(self) -> str:
        return self.bucket_name

    @model_validator(mode="after")
    def safe_mode(self):
        for name in ("provider_image", "provider_read", "provider_conclude", "provider_embed"):
            if name not in self.model_fields_set:
                setattr(self, name, self.ai_provider)
        if self.runtime_mode == "cloud" and not self.enable_cloud:
            raise ValueError("Cloud access requires explicit ENABLE_CLOUD=true authorization")
        if self.runtime_mode != "cloud" and self.ai_mode != "mock":
            raise ValueError("Local/emulator runtimes must use mock AI")
        if self.runtime_mode == "emulator" and not self.project_id.startswith("demo-"):
            raise ValueError("Emulators require a demo- project to prevent production fallback")
        return self


def get_settings() -> Settings:
    """B compatibility: retain explicit runtime opt-in and never auto-read .env."""
    return Settings()
