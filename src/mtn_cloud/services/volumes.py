"""Modern service for MTN Cloud block-storage volume discovery."""

from typing import Any, List

from mtn_cloud.core import CoreClient
from mtn_cloud.models.volume import StorageVolume
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

    def list_attached(self, instance_id: int) -> List[StorageVolume]:
        """List volumes attached to one instance."""

        return self.list(instance_id=instance_id)
