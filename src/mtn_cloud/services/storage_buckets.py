"""Modern service for MTN Cloud S3-compatible storage buckets."""

from typing import Any, List

from pydantic import ValidationError as ModelValidationError

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
        return self._list_page(
            params={key: value for key, value in params.items() if value is not None}
        )

    def list(self, **kwargs: Any) -> List[StorageBucket]:
        return self.list_page(**kwargs).items

    def get(self, bucket_id: int) -> StorageBucket:
        body = self._core.request("GET", f"{self.path}/{bucket_id}")
        return self._parse_item(body, method="GET", bucket_id=bucket_id)

    def get_by_name(self, name: str) -> StorageBucket:
        """Find an exact, unique configuration name across all collection pages."""
        return self._get_by_name("Storage bucket", name)

    def create(self, request: StorageBucketCreate) -> StorageBucket:
        body = self._core.request("POST", self.path, json=request.to_api_payload())
        return self._parse_item(body, method="POST")

    def update(self, bucket_id: int, request: StorageBucketUpdate) -> StorageBucket:
        body = self._core.request(
            "PUT",
            f"{self.path}/{bucket_id}",
            json=request.to_api_payload(),
        )
        return self._parse_item(body, method="PUT", bucket_id=bucket_id)

    def delete(self, bucket_id: int, *, remove_resources: bool = False) -> bool:
        """Remove a configuration; HTTP 404 means it is already absent.

        Underlying provider resources are requested for removal only when
        ``remove_resources=True``. A successful submission does not prove
        asynchronous backend cleanup or removal of S3 objects.
        """
        params = {"removeResources": True} if remove_resources else None
        try:
            body = self._core.request("DELETE", f"{self.path}/{bucket_id}", params=params)
        except NotFoundError:
            return True
        self._check_failure(body, method="DELETE", bucket_id=bucket_id)
        return True

    @classmethod
    def _check_failure(cls, body: Any, *, method: str, bucket_id: int | None) -> None:
        if isinstance(body, dict) and body.get("success") is False:
            raise cls._response_error("Storage-bucket operation was rejected", method, bucket_id)

    @classmethod
    def _parse_item(cls, body: Any, *, method: str, bucket_id: int | None = None) -> StorageBucket:
        cls._check_failure(body, method=method, bucket_id=bucket_id)
        if not isinstance(body, dict):
            raise cls._response_error("Invalid storage-bucket response", method, bucket_id)
        payload = body.get("storageBucket", body)
        if not isinstance(payload, dict):
            raise cls._response_error("Invalid storage-bucket response", method, bucket_id)
        try:
            return StorageBucket.model_validate(payload)
        except ModelValidationError as exc:
            # Configuration and provider errors can contain access credentials.
            # Keep raw validation details on the cause, not the public message.
            raise cls._response_error("Invalid storage-bucket response", method, bucket_id) from exc

    @staticmethod
    def _response_error(message: str, method: str, bucket_id: int | None) -> MtnCloudError:
        return MtnCloudError(
            message,
            method=method,
            path="/storage-buckets" if bucket_id is None else f"/storage-buckets/{bucket_id}",
            response=None if bucket_id is None else {"bucket_id": bucket_id},
        )
