from pydantic import AliasChoices, Field, model_validator
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
    # CURSOR_API_KEY is primary (matches the SDK's own env var name).
    # CURSORPIPE_API_KEY is accepted as an alias for consistency with v1,
    # so users can reuse a v1 .env file without changes.
    cursor_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("CURSOR_API_KEY", "CURSORPIPE_API_KEY"),
    )

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

    # ── Thinking / reasoning ───────────────────────────────────────────────────
    # Controls whether thinking is requested from the SDK AND surfaced in
    # responses (reasoning_content for streaming, cursor_metadata.thinking for
    # non-streaming).
    #
    # Accepted values: "off" | "low" | "high"
    #   off  — do not request thinking; discard any thinking tokens (default)
    #   low  — request thinking=low from the SDK; surface in response
    #   high — request thinking=high from the SDK; surface in response
    #
    # Backward-compat: CURSORPIPE_EXPOSE_THINKING=true maps to thinking_level="high".
    # CURSORPIPE_EXPOSE_THINKING=false (or unset) leaves thinking_level unchanged.
    thinking_level: str = Field(default="off")

    # Internal: read legacy CURSORPIPE_EXPOSE_THINKING and upgrade to thinking_level.
    # Not exposed as a public field — use thinking_level directly.
    _expose_thinking_compat: bool = Field(default=False, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _upgrade_expose_thinking(cls, values: dict) -> dict:
        """Convert legacy CURSORPIPE_EXPOSE_THINKING=true → thinking_level=high."""
        expose = values.get("CURSORPIPE_EXPOSE_THINKING") or values.get("expose_thinking")
        if expose in (True, "true", "1", "yes") and not values.get(
            "CURSORPIPE_THINKING_LEVEL"
        ) and not values.get("thinking_level"):
            values["thinking_level"] = "high"
        return values

    # ── Logging ────────────────────────────────────────────────────────────────
    # Accepts: debug, info, warning, error, critical
    log_level: str = Field(default="info")

    @property
    def thinking_param(self) -> str | None:
        """Return the SDK thinking parameter value, or None if thinking is off."""
        level = self.thinking_level.lower().strip()
        return level if level in ("low", "high") else None

    def cors_origins_list(self) -> list[str]:
        """Parse CURSORPIPE_CORS_ORIGINS into a list for CORSMiddleware."""
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
