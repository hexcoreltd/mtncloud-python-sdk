"""Configuration for the modern MTN Cloud client."""

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_BASE_URL = "https://console.cloud.mtn.ng"
DEFAULT_USER_AGENT = "mtncloud-python-sdk/0.1.0"


class ClientSettings(BaseSettings):
    """Runtime settings for :class:`MtnCloudClient`.

    Explicit constructor values take precedence over ``MTN_CLOUD_*``
    environment variables. Secrets are kept as ``SecretStr`` values until a
    transport explicitly needs the raw value.
    """

    model_config = SettingsConfigDict(
        env_prefix="MTN_CLOUD_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    base_url: str = Field(default=DEFAULT_BASE_URL)
    api_prefix: str = Field(default="/api")
    token: SecretStr | None = Field(default=None)
    api_key: SecretStr | None = Field(default=None)
    api_refresh_token: SecretStr | None = Field(default=None)
    timeout: float = Field(default=30.0, gt=0, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay: float = Field(default=0.5, ge=0, le=60)
    verify_ssl: bool = Field(default=True)
    user_agent: str = Field(default=DEFAULT_USER_AGENT)

    @field_validator("base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("https://", "http://")):
            raise ValueError("base_url must include http:// or https://")
        return value

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        return "/" + value.strip("/")

    @field_validator("user_agent")
    @classmethod
    def validate_user_agent(cls, value: str) -> str:
        value = value.strip()
        if not value or "\r" in value or "\n" in value:
            raise ValueError("user_agent must be non-empty and cannot contain line breaks")
        return value

    @property
    def api_url(self) -> str:
        """Return the normalized control-plane API URL."""

        return f"{self.base_url}{self.api_prefix}"

    def token_value(self) -> str | None:
        """Return the token only when a transport explicitly needs it."""

        if self.token is not None:
            return self.token.get_secret_value()
        return self.api_key.get_secret_value() if self.api_key is not None else None
