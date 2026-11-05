"""Read-only process discovery and polling for explicitly selected statuses."""

import time
from collections.abc import Callable, Collection
from math import isfinite
from typing import Any, List

from pydantic import ValidationError as ModelValidationError

from mtn_cloud.core import CoreClient
from mtn_cloud.models.process import Process
from mtn_cloud.modern_exceptions import MtnCloudError, TimeoutError
from mtn_cloud.services.base import Page, Service


def _positive_id(value: int, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _status(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("status values must be nonempty strings")
    return value.strip().lower()


class _ProcessCollection(Service[Process]):
    """Reuse page decoding without exposing unsupported pagination controls."""

    path = "/processes"
    item_key = "process"
    list_key = "processes"
    model = Process


class ProcessesService:
    """Inspect process history. MTN-specific live verification remains pending."""

    path = "/processes"

    def __init__(
        self,
        core: CoreClient,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._core = core
        self._sleeper = sleeper
        self._clock = clock

    @staticmethod
    def _check_events(process: Process, path: str) -> None:
        if any(event.process_id not in (None, process.id) for event in process.events):
            raise MtnCloudError(
                "Process event references a different parent", method="GET", path=path
            )

    def get(self, process_id: int, *, instance_id: int | None = None) -> Process:
        """Read one process; an optional instance ID requires an explicit match."""
        _positive_id(process_id, "process_id")
        if instance_id is not None:
            _positive_id(instance_id, "instance_id")
        path = f"{self.path}/{process_id}"
        body = self._core.request("GET", path)
        if (
            not isinstance(body, dict)
            or body.get("success") is False
            or not isinstance(body.get("process"), dict)
        ):
            raise MtnCloudError("Invalid process detail response", method="GET", path=path)
        try:
            process = Process.model_validate(body["process"])
        except ModelValidationError as exc:
            raise MtnCloudError("Invalid process detail data", method="GET", path=path) from exc
        if process.id != process_id:
            raise MtnCloudError("Process detail returned a different ID", method="GET", path=path)
        if instance_id is not None and process.instance_id != instance_id:
            raise MtnCloudError(
                "Process does not explicitly reference the requested instance",
                method="GET",
                path=path,
            )
        self._check_events(process, path)
        return process

    def list_page(
        self,
        *,
        instance_id: int | None = None,
        container_id: int | None = None,
        server_id: int | None = None,
        zone_id: int | None = None,
        app_id: int | None = None,
        phrase: str | None = None,
    ) -> Page[Process]:
        """Read a provider-selected history page with documented reference filters.

        Paging metadata is retained, but offset/max query support has not
        been established. This method does not promise complete history.
        """
        filters = {
            "instanceId": instance_id,
            "containerId": container_id,
            "serverId": server_id,
            "zoneId": zone_id,
            "appId": app_id,
        }
        for name, reference in filters.items():
            if reference is not None:
                _positive_id(reference, name)
        params: dict[str, Any] = {key: value for key, value in filters.items() if value is not None}
        if phrase is not None:
            params["phrase"] = phrase
        try:
            page = _ProcessCollection(self._core)._list_page(params=params or None)
        except ModelValidationError as exc:
            raise MtnCloudError(
                "Invalid process collection data", method="GET", path=self.path
            ) from exc
        for process in page.items:
            self._check_events(process, self.path)
            if instance_id is not None and process.instance_id not in (None, instance_id):
                raise MtnCloudError(
                    "Process history references a different instance", method="GET", path=self.path
                )
        return page

    def list(self, **filters: Any) -> List[Process]:
        """Return the current provider-selected page, not an exhaustive history."""
        return self.list_page(**filters).items

    def wait_for_status(
        self,
        process_id: int,
        target_status: str,
        *,
        instance_id: int | None = None,
        failure_statuses: Collection[str] = (),
        timeout: float = 300,
        poll_interval: float = 5,
        on_status: Callable[[Process], None] | None = None,
    ) -> Process:
        """Poll until a caller-selected status matches, ignoring case/outer spaces.

        There are no implicit success/failure labels. Request timeouts and
        core GET retries may extend this polling budget.
        """
        _positive_id(process_id, "process_id")
        if instance_id is not None:
            _positive_id(instance_id, "instance_id")
        target = _status(target_status)
        if not isinstance(failure_statuses, Collection) or isinstance(
            failure_statuses, (str, bytes)
        ):
            raise ValueError("failure_statuses must be a collection of status strings")
        failures = {_status(item) for item in failure_statuses}
        if target in failures:
            raise ValueError("target_status must not also be a failure status")
        if any(
            type(value) not in (int, float) or not isfinite(value) or value <= 0
            for value in (timeout, poll_interval)
        ):
            raise ValueError("timeout and poll_interval must be finite and positive")
        deadline = self._clock() + timeout
        last_status: str | None = None
        observed = False
        path = f"{self.path}/{process_id}"
        while not observed or self._clock() < deadline:
            process = self.get(process_id, instance_id=instance_id)
            observed = True
            last_status = process.status
            current = last_status.strip().lower() if last_status is not None else None
            if on_status is not None:
                on_status(process)
            if current == target:
                return process
            if current in failures:
                raise MtnCloudError(
                    "Process reached a caller-designated failure status",
                    method="GET",
                    path=path,
                    response={"process_id": process_id, "last_status": last_status},
                )
            remaining = deadline - self._clock()
            if remaining <= 0:
                break
            self._sleeper(min(poll_interval, remaining))
        raise TimeoutError(
            "Timed out waiting for the requested process status",
            timeout=timeout,
            method="GET",
            path=path,
            response={"process_id": process_id, "last_status": last_status},
        )
