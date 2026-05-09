"""Typed runtime configuration loaded from environment variables.

All Aurelia-specific knobs live in :class:`Settings`. Third-party SDKs that read
their own env vars directly (LiveKit, OpenAI, Deepgram, Google) still do so —
this module just centralizes the values *we* read in our code, validates them
once at startup, and gives the rest of the codebase a typed accessor.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Env = Literal["dev", "prod"]


class Settings(BaseSettings):
    """Application settings.

    Values come from environment variables (and optionally a `.env` file in the
    working directory). Field names map to env var names case-insensitively.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Runtime ----
    aurelia_env: Env = Field(default="dev", description="dev or prod runtime profile.")
    aurelia_log_level: str = Field(default="INFO")

    # ---- Persona ----
    aurelia_company_name: str = Field(default="Northwind Heating & Cooling")
    aurelia_agent_name: str = Field(default="Aurelia")
    aurelia_business_hours: str = Field(default="Monday through Friday, 7am to 6pm")

    # ---- LiveKit ----
    # The LiveKit Agents SDK reads these directly, but we surface them so
    # startup can fail fast if they're missing rather than mid-call.
    livekit_url: str = Field(default="")
    livekit_api_key: SecretStr = Field(default=SecretStr(""))
    livekit_api_secret: SecretStr = Field(default=SecretStr(""))

    # ---- Model providers ----
    openai_api_key: SecretStr = Field(default=SecretStr(""))
    openai_llm_model: str = Field(default="gpt-4o-mini")
    openai_tts_model: str = Field(default="gpt-4o-mini-tts")
    openai_tts_voice: str = Field(default="shimmer")
    deepgram_api_key: SecretStr = Field(default=SecretStr(""))
    deepgram_stt_model: str = Field(default="nova-3")

    # ---- Google Sheets ----
    google_service_account_json: SecretStr = Field(
        default=SecretStr(""),
        description="Inline JSON content for a service-account key. Wins over the file path.",
    )
    google_service_account_file: Path | None = Field(
        default=None,
        description="Path to a service-account JSON key file.",
    )
    google_sheets_spreadsheet_id: str = Field(default="")
    google_sheets_worksheet_name: str = Field(default="Intakes")

    # ---- Escalation ----
    escalation_enabled: bool = Field(default=True)
    escalation_email_to: str = Field(default="")
    escalation_email_from: str = Field(default="")
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_username: str = Field(default="")
    smtp_password: SecretStr = Field(default=SecretStr(""))
    smtp_use_tls: bool = Field(default=True)

    # ---- Validators ----

    @model_validator(mode="after")
    def _check_sheets_credentials_consistency(self) -> Settings:
        """If a service-account file path is provided, it must exist.

        We don't *require* credentials at config-load time (tests and dev mode
        often run without them); we only flag the case where a path is set but
        wrong, since that's almost always a typo.
        """
        if self.google_service_account_file is not None:
            path = self.google_service_account_file
            if not path.exists():
                raise ValueError(
                    f"GOOGLE_SERVICE_ACCOUNT_FILE points to {path}, which does not exist."
                )
        return self

    # ---- Convenience ----

    @property
    def is_prod(self) -> bool:
        return self.aurelia_env == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` instance.

    Cached so config is parsed once. Tests that need a fresh instance should
    call :func:`get_settings.cache_clear` after mutating the environment.
    """
    return Settings()
