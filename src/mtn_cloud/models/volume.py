"""Models for MTN Cloud storage volumes."""

from typing import Any

from pydantic import Field

from mtn_cloud.models.base import Resource


class StorageVolume(Resource):
    """
    MTN Cloud storage volume.

    Represents a block storage volume that can be attached to instances.
    """

    description: str | None = Field(default=None)

    size: int | None = Field(default=None, alias="maxStorage", description="Size in bytes")
    size_gb: int | None = Field(default=None, description="Size in GB")

    storage_type: dict[str, Any] | None = Field(default=None, alias="storageType")
    volume_type: str | None = Field(default=None, alias="volumeType")

    status: str | None = Field(default=None, description="Volume status")

    instance_id: int | None = Field(default=None, alias="instanceId")
    device_name: str | None = Field(default=None, alias="deviceName")

    root_volume: bool = Field(default=False, alias="rootVolume")

    datastore: dict[str, Any] | None = Field(default=None)
    datastore_id: str | None = Field(default=None, alias="datastoreId")

    zone: dict[str, Any] | None = Field(default=None)

    external_id: str | None = Field(default=None, alias="externalId")

    @property
    def is_attached(self) -> bool:
        """Check if volume is attached to an instance."""
        return self.instance_id is not None

    @property
    def is_available(self) -> bool:
        """Return whether the volume appears available for attachment."""

        return not self.is_attached and (self.status or "").lower() in {
            "",
            "available",
            "provisioned",
            "ready",
        }


# Backwards-compatible name retained for earlier SDK versions.
Volume = StorageVolume


class StorageVolumeType(Resource):
    """A storage-volume provider type and its configurable options."""

    category: str | None = None
    code: str | None = None
    description: str | None = None
    enabled: bool = True
    default_type: bool = Field(default=False, alias="defaultType")
    custom_label: bool = Field(default=False, alias="customLabel")
    custom_size: bool = Field(default=False, alias="customSize")
    configurable_iops: bool = Field(default=False, alias="configurableIOPS")
    has_datastore: bool = Field(default=False, alias="hasDatastore")
    option_types: list[dict[str, Any]] = Field(default_factory=list, alias="optionTypes")
