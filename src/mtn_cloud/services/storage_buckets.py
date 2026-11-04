"""Modern service for MTN Cloud S3-compatible storage buckets."""

from typing import Any, List

from mtn_cloud.core import CoreClient
from mtn_cloud.models.storage_bucket import (
    StorageBucket,
    StorageBucketCreate,
    StorageBucketUpdate,
)
from mtn_cloud.modern_exceptions import MtnCloudError, NotFoundError
from mtn_cloud.services.base import Page, Service


class StorageBucketsService(Service[StorageBucket]):
    """Manage MTN Cloud storage-provider bucket configurations."""

    path = "/storage-buckets"
    item_key = "storageBucket"
    list_key = "storageBuckets"
    model = StorageBucket

    def list_page(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        phrase: str | None = None,
        name: str | None = None,
    ) -> Page[StorageBucket]:
        params = {"max": limit, "offset": offset, "phrase": phrase, "name": name}
        return self._list_page(params={key: value for key, value in params.items() if value is not None})

    def list(self, **kwargs: Any) -> List[StorageBucket]:
        return self.list_page(**kwargs).items

    def get(self, bucket_id: int) -> StorageBucket:
        return self._get(bucket_id)

    def get_by_name(self, name: str) -> StorageBucket:
        matches = [bucket for bucket in self.list(name=name, limit=100) if bucket.name == name]
        if not matches:
            raise NotFoundError(f"Storage bucket '{name}' not found")
        if len(matches) > 1:
            raise ValueError(f"Storage bucket '{name}' is ambiguous")
        return matches[0]

    def create(self, request: StorageBucketCreate) -> StorageBucket:
        body = self._core.request("POST", self.path, json=request.to_api_payload())
        return self._parse_item(body)

    def update(self, bucket_id: int, request: StorageBucketUpdate) -> StorageBucket:
        body = self._core.request(
            "PUT",
            f"{self.path}/{bucket_id}",
            json=request.to_api_payload(),
        )
        return self._parse_item(body)

    def delete(self, bucket_id: int, *, remove_resources: bool = False) -> bool:
        params = {"removeResources": True} if remove_resources else None
        self._core.request("DELETE", f"{self.path}/{bucket_id}", params=params)
        return True

    @staticmethod
    def _parse_item(body: Any) -> StorageBucket:
        if not isinstance(body, dict):
            raise MtnCloudError("Invalid storage-bucket response")
        payload = body.get("storageBucket", body)
        if not isinstance(payload, dict):
            raise MtnCloudError("Invalid storage-bucket response")
        return StorageBucket.model_validate(payload)
