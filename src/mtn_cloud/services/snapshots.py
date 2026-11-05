"""Snapshot resource adapters based on the upstream Morpheus contract."""

from typing import Any

from mtn_cloud.core import CoreClient
from mtn_cloud.models.snapshot import Snapshot
from mtn_cloud.modern_exceptions import MtnCloudError


def validate_snapshot_id(value: int, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def require_snapshot_success(body: Any, *, method: str, path: str) -> None:
    """An explicit success acknowledges submission, not provider completion."""
    if not isinstance(body, dict) or body.get("success") is not True:
        raise MtnCloudError("Snapshot operation did not return success", method=method, path=path)


class SnapshotsService:
    """Retrieve or explicitly delete a snapshot by its global resource ID.

    Use ``instances.delete_snapshot`` when deletion must check membership in
    an instance's snapshot collection first. MTN live verification is pending.
    """

    path = "/snapshots"

    def __init__(self, core: CoreClient) -> None:
        self._core = core

    def get(self, snapshot_id: int) -> Snapshot:
        validate_snapshot_id(snapshot_id, "snapshot_id")
        path = f"{self.path}/{snapshot_id}"
        body = self._core.request("GET", path)
        if (
            not isinstance(body, dict)
            or body.get("success") is False
            or not isinstance(body.get("snapshot"), dict)
        ):
            raise MtnCloudError("Invalid snapshot detail response", method="GET", path=path)
        if type(body["snapshot"].get("id")) is not int:
            raise MtnCloudError("Invalid snapshot identifier", method="GET", path=path)
        snapshot = Snapshot.model_validate(body["snapshot"])
        if snapshot.id != snapshot_id:
            raise MtnCloudError("Snapshot detail returned a different ID", method="GET", path=path)
        return snapshot

    def delete(self, snapshot_id: int) -> bool:
        """Request deletion by ID; True records acknowledgement only."""
        validate_snapshot_id(snapshot_id, "snapshot_id")
        path = f"{self.path}/{snapshot_id}"
        body = self._core.request("DELETE", path)
        require_snapshot_success(body, method="DELETE", path=path)
        return True
