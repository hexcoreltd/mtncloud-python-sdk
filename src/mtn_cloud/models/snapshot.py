"""Models for MTN Cloud snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import ConfigDict, Field

from mtn_cloud.models.base import BaseModel, Resource


class Snapshot(Resource):
    """
    MTN Cloud instance snapshot.

    Snapshots capture the disk state of an instance at a point in time.
    They are accessed via the instance they belong to.

    Creation returns a submission rather than this resource. Discover the
    snapshot separately after the provider has completed the operation.
    """

    model_config = ConfigDict(hide_input_in_errors=True)

    description: str | None = Field(default=None, repr=False)
    status: str | None = None
    snapshot_type: str | None = Field(default=None, alias="snapshotType")
    snapshot_created: datetime | None = Field(default=None, alias="snapshotCreated")
    current: bool | None = None
    currently_active: bool | None = Field(default=None, alias="currentlyActive")
    memory_snapshot: bool | None = Field(default=None, alias="memorySnapshot")
    for_export: bool | None = Field(default=None, alias="forExport")
    for_backup: bool | None = Field(default=None, alias="forBackup")
    max_storage: int | None = Field(default=None, alias="maxStorage")
    parent_snapshot: str | None = Field(default=None, alias="parentSnapshot")
    snapshot_files: list[dict[str, Any]] = Field(
        default_factory=list, alias="snapshotFiles", repr=False
    )
    external_id: str | None = Field(default=None, alias="externalId")
    state: str | dict[str, Any] | None = Field(default=None, repr=False)
    datastore: str | dict[str, Any] | None = Field(default=None, repr=False)
    zone: dict[str, Any] | None = None
    instance: dict[str, Any] | None = None

    @property
    def cloud_id(self) -> int | None:
        if self.zone:
            return self.zone.get("id")
        return None


class SnapshotCreate(BaseModel):
    """Payload builder for creating a snapshot."""

    model_config = ConfigDict(hide_input_in_errors=True)

    name: str = Field(min_length=1)
    description: str | None = Field(default=None, repr=False)
    memory_snapshot: bool | None = Field(default=None, alias="memorySnapshot")
    for_export: bool | None = Field(default=None, alias="forExport")

    def to_api_payload(self) -> dict[str, Any]:
        return {"snapshot": self.model_dump(by_alias=True, exclude_none=True)}


class SnapshotSubmission(BaseModel):
    """Accepted asynchronous snapshot request, not a completed snapshot.

    Process IDs identify operations, not snapshot resources. An empty list
    supplies no tracking identifiers and does not prove completion.
    """

    model_config = ConfigDict(hide_input_in_errors=True)

    instance_id: Annotated[int, Field(strict=True, gt=0)]
    process_ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(alias="processIds")
