"""Read-only virtual-image discovery using the existing Morpheus collection."""

from typing import Any, List, Literal

from mtn_cloud.models.virtual_image import VirtualImage
from mtn_cloud.services.base import Page, Service

ImageFilterType = Literal["User", "System", "Synced", "All"]


class VirtualImagesService(Service[VirtualImage]):
    """Discover image metadata; MTN-specific live validation remains pending."""

    path = "/virtual-images"
    item_key = "virtualImage"
    list_key = "virtualImages"
    model = VirtualImage

    def list_page(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        name: str | None = None,
        phrase: str | None = None,
        image_type: str | None = None,
        filter_type: ImageFilterType | None = None,
    ) -> Page[VirtualImage]:
        """Return one page, optionally filtered by name, format or image origin.

        ``filter_type`` selects User/System/Synced/All images, not visibility.
        Omission retains the provider's default scope.
        """
        if limit is not None and (type(limit) is not int or limit < 1):
            raise ValueError("limit must be a positive integer")
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be a non-negative integer")
        if filter_type is not None and filter_type not in ("User", "System", "Synced", "All"):
            raise ValueError("filter_type must be User, System, Synced or All")
        params = {
            "max": limit,
            "offset": offset,
            "name": name,
            "phrase": phrase,
            "imageType": image_type,
            "filterType": filter_type,
        }
        return self._list_page(
            params={key: value for key, value in params.items() if value is not None}
        )

    def list(self, **kwargs: Any) -> List[VirtualImage]:
        """Return one page of images; use ``list_all`` to traverse all pages."""
        return self.list_page(**kwargs).items

    def get(self, virtual_image_id: int) -> VirtualImage:
        """Retrieve image metadata by positive integer ID."""
        if type(virtual_image_id) is not int or virtual_image_id < 1:
            raise ValueError("virtual_image_id must be a positive integer")
        return self._get(virtual_image_id)

    def get_by_name(
        self,
        name: str,
        *,
        image_type: str | None = None,
        filter_type: ImageFilterType | None = None,
    ) -> VirtualImage:
        """Require one exact name match across every page in the selected scope."""
        return self._get_by_name(
            "Virtual image", name, image_type=image_type, filter_type=filter_type
        )
