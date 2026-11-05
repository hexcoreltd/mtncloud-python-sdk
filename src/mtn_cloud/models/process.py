"""Process history and event models; status strings retain provider meaning."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import ConfigDict, Field

from mtn_cloud.models.base import Resource


class _ProcessRecord(Resource):
    model_config = ConfigDict(hide_input_in_errors=True, str_strip_whitespace=False)

    id: Annotated[int, Field(strict=True, gt=0)]
    account_id: int | None = Field(default=None, alias="accountId")
    unique_id: str | None = Field(default=None, alias="uniqueId")
    process_type: dict[str, Any] | None = Field(default=None, alias="processType", repr=False)
    display_name: str | None = Field(default=None, alias="displayName", repr=False)
    description: str | None = Field(default=None, repr=False)
    sub_type: str | None = Field(default=None, alias="subType")
    sub_id: int | str | None = Field(default=None, alias="subId")
    zone_id: int | None = Field(default=None, alias="zoneId")
    integration_id: str | None = Field(default=None, alias="integrationId")
    instance_id: Annotated[int, Field(strict=True)] | None = Field(default=None, alias="instanceId")
    container_id: int | None = Field(default=None, alias="containerId")
    server_id: int | None = Field(default=None, alias="serverId")
    container_name: str | None = Field(default=None, alias="containerName", repr=False)
    status: str | None = None
    reason: str | None = Field(default=None, repr=False)
    percent: float | None = None
    status_eta: int | None = Field(default=None, alias="statusEta")
    message: str | None = Field(default=None, repr=False)
    output: str | None = Field(default=None, repr=False)
    error: str | None = Field(default=None, repr=False)
    start_date: datetime | None = Field(default=None, alias="startDate")
    end_date: datetime | None = Field(default=None, alias="endDate")
    duration: int | None = None
    created_by: dict[str, Any] | None = Field(default=None, alias="createdBy", repr=False)
    updated_by: dict[str, Any] | None = Field(default=None, alias="updatedBy", repr=False)

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id})"


class ProcessEvent(_ProcessRecord):
    """An event within a process; logs remain available but hidden from repr."""

    process_id: Annotated[int, Field(strict=True, gt=0)] | None = Field(
        default=None, alias="processId"
    )
    ref_type: str | None = Field(default=None, alias="refType")
    ref_id: int | None = Field(default=None, alias="refId")


class Process(_ProcessRecord):
    """An asynchronous operation record, not evidence of resource readiness."""

    app_id: str | None = Field(default=None, alias="appId")
    result_type: str | None = Field(default=None, alias="resultType")
    result_id: int | None = Field(default=None, alias="resultId")
    events: list[ProcessEvent] = Field(default_factory=list, repr=False)
