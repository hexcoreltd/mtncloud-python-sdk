"""Modern service for MTN Cloud block-storage volume discovery."""

from typing import Any, List

from mtn_cloud.core import CoreClient
from mtn_cloud.models.volume import StorageVolume, StorageVolumeType
from mtn_cloud.modern_exceptions import MtnCloudError
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
        return self._list_page(params={key: value for key, value in params.items() if value is not None})

    def list(self, **kwargs: Any) -> List[StorageVolume]:
        return self.list_page(**kwargs).items

    def get(self, volume_id: int) -> StorageVolume:
        return self._get(volume_id)

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
        """List volumes attached to one instance."""

        return self.list(instance_id=instance_id)
