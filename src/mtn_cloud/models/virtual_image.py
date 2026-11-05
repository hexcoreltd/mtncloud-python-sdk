"""Models for MTN Cloud virtual images."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import ConfigDict, Field

from mtn_cloud.models.base import BaseModel, Resource


class VirtualImageTag(BaseModel):
    """Name/value metadata tag returned by the upstream image API."""

    model_config = ConfigDict(hide_input_in_errors=True)

    name: str
    value: str | None = Field(default=None, repr=False)


class VirtualImage(Resource):
    """
    MTN Cloud virtual image.

    Represents a VM image (template) that can be used when provisioning
    instances. Includes both system-provided and user-uploaded images.

    Example:
        images = cloud.virtual_images.list()
        for img in images:
            print(f"{img.name}: {img.image_type} ({img.status})")
    """

    model_config = ConfigDict(hide_input_in_errors=True)

    image_type: str | None = Field(default=None, alias="imageType")
    image_path: str | None = Field(default=None, alias="imagePath")
    status: str | None = None
    is_public: bool | None = Field(default=None, alias="isPublic")
    visibility: str | None = None
    user_uploaded: bool | None = Field(default=None, alias="userUploaded")
    user_defined: bool | None = Field(default=None, alias="userDefined")
    system_image: bool | None = Field(default=None, alias="systemImage")
    is_cloud_init: bool | None = Field(default=None, alias="isCloudInit")
    is_auto_join_domain: bool | None = Field(default=None, alias="isAutoJoinDomain")
    user_data: str | None = Field(default=None, alias="userData", repr=False)
    storage_provider: dict[str, Any] | None = Field(
        default=None, alias="storageProvider", repr=False
    )
    min_disk: int | None = Field(default=None, alias="minDisk")
    min_ram: int | None = Field(default=None, alias="minRam")
    raw_size: int | None = Field(default=None, alias="rawSize")
    external_id: str | None = Field(default=None, alias="externalId")
    owner_id: int | None = Field(default=None, alias="ownerId")
    tenant: dict[str, Any] | None = None
    locations: list[dict[str, Any]] = Field(default_factory=list, repr=False)
    tags: list[str | VirtualImageTag] = Field(default_factory=list, repr=False)
    labels: list[str] = Field(default_factory=list)
    os_type: dict[str, Any] | None = Field(default=None, alias="osType")
    date_created: datetime | None = Field(default=None, alias="dateCreated")
    last_updated: datetime | None = Field(default=None, alias="lastUpdated")

    @property
    def os_name(self) -> str | None:
        if self.os_type:
            return self.os_type.get("name")
        return None

    @property
    def os_code(self) -> str | None:
        if self.os_type:
            return self.os_type.get("code")
        return None
