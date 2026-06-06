from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CURSORPIPE_",
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    # ── Cursor auth ────────────────────────────────────────────────────────────
    # Read without prefix so it matches CURSOR_API_KEY used by the SDK itself.
    cursor_api_key: str = Field(default="", alias="CURSOR_API_KEY")

    # ── Server ─────────────────────────────────────────────────────────────────
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8080)

    # Optional bearer token clients must send in Authorization header.
    # Empty string disables auth.
    bearer_token: str = Field(default="")

    # Comma-separated allowed CORS origins. "*" allows all.
    cors_origins: str = Field(default="*")

    # ── Agent ──────────────────────────────────────────────────────────────────
    model: str = Field(default="composer-2.5")

    # Working directory passed to LocalAgentOptions.
    workspace: str = Field(default=".")

    # ── Stateful sessions ──────────────────────────────────────────────────────
    session_ttl_minutes: int = Field(default=30)

    # ── Features ───────────────────────────────────────────────────────────────
    # When true, thinking/reasoning content is included in responses as
    # reasoning_content (streaming) or cursor_metadata.thinking (non-streaming).
    expose_thinking: bool = Field(default=False)

    # ── Logging ────────────────────────────────────────────────────────────────
    # Accepts: debug, info, warning, error, critical
    log_level: str = Field(default="info")

    def cors_origins_list(self) -> list[str]:
        """Parse CURSORPIPE_CORS_ORIGINS into a list for CORSMiddleware."""
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
