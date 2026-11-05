"""Modern service for MTN Cloud block-storage volume discovery."""

from typing import Any, List

from mtn_cloud.models.volume import StorageVolume, StorageVolumeType
from mtn_cloud.modern_exceptions import AmbiguousLookupError, LookupNotFoundError, MtnCloudError
from mtn_cloud.services.base import Page, Service


class VolumesService(Service[StorageVolume]):
    """Discover tenant block-storage volumes."""

    path = "/storage/volumes"
    item_key = "storageVolume"
    list_key = "storageVolumes"
    model = StorageVolume

    def list_page(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        phrase: str | None = None,
        instance_id: int | None = None,
        zone_id: int | None = None,
    ) -> Page[StorageVolume]:
        """List volumes with optional instance and zone filters."""

        params = {
            "max": limit,
            "offset": offset,
            "phrase": phrase,
            "instanceId": instance_id,
            "zoneId": zone_id,
        }
        return self._list_page(
            params={key: value for key, value in params.items() if value is not None}
        )

    def list(self, **kwargs: Any) -> List[StorageVolume]:
        return self.list_page(**kwargs).items

    def get(self, volume_id: int) -> StorageVolume:
        return self._get(volume_id)

    def get_by_name(self, name: str, *, zone_id: int | None = None) -> StorageVolume:
        """Find an exact name across every page, optionally scoped to a zone."""

        matches = [
            volume for volume in self.list_all(phrase=name, zone_id=zone_id) if volume.name == name
        ]
        if not matches:
            raise LookupNotFoundError(f"Storage volume '{name}' was not found")
        if len(matches) > 1:
            ids = sorted(volume.id for volume in matches)
            raise AmbiguousLookupError(f"Storage volume name '{name}' is ambiguous: ids {ids}")
        return matches[0]

    def list_types(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        category: str = "volume",
        enabled_only: bool = True,
    ) -> List[StorageVolumeType]:
        """List storage volume types and their provider-specific options."""

        params = {"max": limit, "offset": offset, "category": category}
        body = self._core.request(
            "GET",
            "/storage/volume-types",
            params={key: value for key, value in params.items() if value is not None},
        )
        if not isinstance(body, dict) or not isinstance(body.get("storageVolumeTypes"), list):
            raise MtnCloudError("Invalid storage-volume-type response")
        types = [StorageVolumeType.model_validate(item) for item in body["storageVolumeTypes"]]
        return [item for item in types if not enabled_only or item.enabled]

    def get_type(self, volume_type_id: int) -> StorageVolumeType:
        """Retrieve one storage-volume type by ID."""

        body = self._core.request("GET", f"/storage/volume-types/{volume_type_id}")
        if not isinstance(body, dict):
            raise MtnCloudError("Invalid storage-volume-type response")
        return StorageVolumeType.model_validate(body.get("storageVolumeType", body))

    def list_attached(self, instance_id: int) -> List[StorageVolume]:
        """List all pages of volumes filtered by an instance ID."""

        return self.list_all(instance_id=instance_id)

    def list_unattached(self, *, zone_id: int | None = None) -> List[StorageVolume]:
        """List all volumes explicitly reporting no instance ID.

        Volumes with omitted attachment data are excluded. Unattached does not
        imply ready for use; inspect status and the ``is_available`` hint too.
        """

        return [volume for volume in self.list_all(zone_id=zone_id) if volume.is_unattached]
