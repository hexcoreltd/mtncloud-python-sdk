"""Resource registry: one entry per resource the CLI can list and describe."""

from __future__ import annotations

from collections.abc import Callable
from copy import copy
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from mtn_cloud import MtnCloudClient
from mtn_cloud.cli import output
from mtn_cloud.models.storage_bucket import StorageBucket
from mtn_cloud.models.volume import StorageVolume
from mtn_cloud.modern_exceptions import MtnCloudError


@dataclass(frozen=True)
class Column:
    header: str
    value: Callable[[Any], object]


@dataclass(frozen=True)
class ResourceSpec:
    name: str
    service: Callable[[MtnCloudClient], Any]
    columns: tuple[Column, ...]
    exclude: frozenset[str] = frozenset()
    supports_group: bool = True
    supports_zone: bool = True
    name_filter: str = "name"
    inventory_default: bool = True
    serializer: Callable[[Any], dict[str, Any]] | None = None
    redact_errors: bool = False

    def dump_item(self, model: BaseModel) -> dict[str, Any]:
        if self.serializer is not None:
            return self.serializer(model)
        return output.dump_item(model, self.exclude)

    def error_for_output(self, error: MtnCloudError) -> MtnCloudError:
        """Keep error type/metadata without provider messages or payloads."""
        if not self.redact_errors:
            return error
        safe = copy(error)
        safe.message = (
            "Storage-bucket operation failed; inspect credentials and permissions securely."
        )
        safe.args = (safe.message,)
        safe.response = None
        return safe


def _network_type(network: Any) -> object:
    return network.type.name if network.type is not None else ""


def _serialize_volume(volume: StorageVolume) -> dict[str, Any]:
    """Emit scalar fields and retain omission versus null attachment evidence."""
    return {
        **volume.model_dump(
            mode="json",
            exclude_unset=True,
            include={
                "id",
                "name",
                "status",
                "size",
                "size_gb",
                "instance_id",
                "root_volume",
                "device_name",
                "external_id",
                "date_created",
                "last_updated",
            },
        ),
        "attachment_state": volume.attachment_state,
        "is_unattached": volume.is_unattached,
        "is_available": volume.is_available,
    }


def _serialize_storage_bucket(bucket: StorageBucket) -> dict[str, Any]:
    """Expose operational scalar fields without provider credentials or metadata."""
    return bucket.model_dump(
        mode="json",
        exclude_unset=True,
        include={
            "id",
            "name",
            "provider_type",
            "bucket_name",
            "active",
            "read_only",
            "copy_to_store",
            "default_backup_target",
            "default_deployment_target",
            "default_virtual_image_target",
            "retention_policy_type",
            "retention_policy_days",
            "date_created",
            "last_updated",
        },
    )


REGISTRY: dict[str, ResourceSpec] = {
    "instances": ResourceSpec(
        name="instances",
        service=lambda client: client.instances,
        columns=(
            Column("ID", lambda m: m.id),
            Column("NAME", lambda m: m.name),
            Column("STATUS", lambda m: m.status),
            Column("IP", lambda m: m.ip_address),
        ),
        # Instance.config can carry customOptions such as passwords; never emit it.
        exclude=frozenset({"config"}),
    ),
    "networks": ResourceSpec(
        name="networks",
        service=lambda client: client.networks,
        columns=(
            Column("ID", lambda m: m.id),
            Column("NAME", lambda m: m.name),
            Column("CIDR", lambda m: m.cidr),
            Column("TYPE", _network_type),
        ),
        exclude=frozenset({"config"}),
    ),
    "routers": ResourceSpec(
        name="routers",
        service=lambda client: client.routers,
        columns=(
            Column("ID", lambda m: m.id),
            Column("NAME", lambda m: m.name),
            Column("STATUS", lambda m: m.status),
            Column("EXTERNAL IP", lambda m: m.external_ip),
        ),
    ),
    "volumes": ResourceSpec(
        name="volumes",
        service=lambda client: client.volumes,
        columns=(
            Column("ID", lambda m: m.id),
            Column("NAME", lambda m: m.name),
            Column("STATUS", lambda m: m.status),
            Column("BYTES", lambda m: m.size),
            Column("ATTACHMENT", lambda m: m.attachment_state),
            Column("INSTANCE", lambda m: m.instance_id),
        ),
        supports_group=False,
        name_filter="phrase",
        inventory_default=False,
        serializer=_serialize_volume,
    ),
    "storage-buckets": ResourceSpec(
        name="storage-buckets",
        service=lambda client: client.storage_buckets,
        columns=(
            Column("ID", lambda m: m.id),
            Column("NAME", lambda m: m.name),
            Column("PROVIDER", lambda m: m.provider_type),
            Column("BUCKET", lambda m: m.bucket_name),
            Column("ACTIVE", lambda m: m.active),
        ),
        supports_group=False,
        supports_zone=False,
        inventory_default=False,
        serializer=_serialize_storage_bucket,
        redact_errors=True,
    ),
}
