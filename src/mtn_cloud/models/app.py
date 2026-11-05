"""Models for MTN Cloud provisioned applications."""

from typing import Any

from pydantic import ConfigDict, Field

from mtn_cloud.models.base import Resource


class Application(Resource):
    """A provisioned MTN Cloud application or catalog deployment."""

    model_config = ConfigDict(hide_input_in_errors=True)

    code: str | None = None
    description: str | None = None
    status: str | None = None
    app_type: str | None = Field(default=None, alias="type")
    category: str | None = None
    environment: str | None = None
    group: dict[str, Any] | None = None
    cloud: dict[str, Any] | None = None
    instances: list[dict[str, Any]] = Field(default_factory=list)
    config: dict[str, Any] | None = Field(default=None, repr=False)

    @property
    def is_running(self) -> bool:
        """Return whether the application reports a running state."""

        return (self.status or "").lower() in {"running", "active", "healthy"}
