"""Modern service for configured backups and backup executions."""

from typing import Any, List

from mtn_cloud.core import CoreClient
from mtn_cloud.models.backup import Backup, BackupJob, BackupResult
from mtn_cloud.modern_exceptions import MtnCloudError
from mtn_cloud.services.base import Page, Service


def _validate_pagination(limit: int | None, offset: int) -> None:
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("limit must be a positive integer")
    if type(offset) is not int or offset < 0:
        raise ValueError("offset must be a non-negative integer")


class _BackupResultsService(Service[BackupResult]):
    """Use the common pagination adapter for a backup's result collection."""

    item_key = "result"
    list_key = "results"
    model = BackupResult

    def __init__(self, core: CoreClient, backup_id: int) -> None:
        super().__init__(core)
        self._backup_id = backup_id
        self.path = f"/backups/{backup_id}/results"

    def list_page(self, *, limit: int | None = None, offset: int = 0) -> Page[BackupResult]:
        _validate_pagination(limit, offset)
        params: dict[str, Any] = {}
        if limit is not None:
            params["max"] = limit
        if offset:
            params["offset"] = offset
        page = self._list_page(params=params or None)
        if any(result.backup_id not in (None, self._backup_id) for result in page.items):
            raise MtnCloudError(
                "Backup result references a different parent backup", method="GET", path=self.path
            )
        return page


class _BackupJobsService(Service[BackupJob]):
    """Use the common pagination/detail adapters for backup job definitions."""

    path = "/backups/jobs"
    item_key = "job"
    list_key = "jobs"
    model = BackupJob

    def list_page(self, *, limit: int | None = None, offset: int = 0) -> Page[BackupJob]:
        _validate_pagination(limit, offset)
        return self._list_page(params={"max": limit, "offset": offset})

    def get(self, job_id: int) -> BackupJob:
        return self._get(job_id)


class BackupsService(Service[Backup]):
    """Inspect backup configurations, jobs, and execution results."""

    path = "/backups"
    item_key = "backup"
    list_key = "backups"
    model = Backup

    def list_page(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        phrase: str | None = None,
    ) -> Page[Backup]:
        _validate_pagination(limit, offset)
        params = {"max": limit, "offset": offset, "phrase": phrase}
        return self._list_page(
            params={key: value for key, value in params.items() if value is not None}
        )

    def list(self, **kwargs: Any) -> List[Backup]:
        return self.list_page(**kwargs).items

    def get(self, backup_id: int) -> Backup:
        return self._get(backup_id)

    def delete(self, backup_id: int) -> bool:
        """Request configuration deletion; provider retention effects require verification."""
        path = f"{self.path}/{backup_id}"
        body = self._core.request("DELETE", path)
        self._check_rejection(body, method="DELETE", path=path)
        return True

    def execute(self, backup_id: int) -> dict[str, Any]:
        """Submit a backup execution; the response does not prove completion."""

        path = f"{self.path}/{backup_id}/execute"
        body = self._core.request("POST", path)
        self._check_rejection(body, method="POST", path=path)
        if not isinstance(body, dict):
            raise MtnCloudError("Invalid backup execution response", method="POST", path=path)
        return body

    def list_results(
        self, backup_id: int, *, limit: int | None = None, offset: int = 0
    ) -> List[BackupResult]:
        """Return one result page; use list_all_results for full history."""
        return self.list_results_page(backup_id, limit=limit, offset=offset).items

    def list_results_page(
        self, backup_id: int, *, limit: int | None = None, offset: int = 0
    ) -> Page[BackupResult]:
        """Return a result page with offset, limit and total metadata."""
        return _BackupResultsService(self._core, backup_id).list_page(limit=limit, offset=offset)

    def list_all_results(self, backup_id: int, *, page_size: int = 100) -> List[BackupResult]:
        """Follow result pages; API errors propagate without returning partial history."""
        return _BackupResultsService(self._core, backup_id).list_all(page_size=page_size)

    def list_jobs(self, *, limit: int | None = None, offset: int = 0) -> List[BackupJob]:
        """Return one page of job definitions, not execution outcomes."""
        return self.list_jobs_page(limit=limit, offset=offset).items

    def list_jobs_page(self, *, limit: int | None = None, offset: int = 0) -> Page[BackupJob]:
        return _BackupJobsService(self._core).list_page(limit=limit, offset=offset)

    def list_all_jobs(self, *, page_size: int = 100) -> List[BackupJob]:
        """Follow all pages of job definitions."""
        return _BackupJobsService(self._core).list_all(page_size=page_size)

    def get_job(self, job_id: int) -> BackupJob:
        return _BackupJobsService(self._core).get(job_id)

    def execute_job(self, job_id: int) -> dict[str, Any]:
        """Submit a job execution without interpreting it as successful recovery."""
        path = f"{self.path}/jobs/{job_id}/execute"
        body = self._core.request("POST", path)
        self._check_rejection(body, method="POST", path=path)
        if not isinstance(body, dict):
            raise MtnCloudError("Invalid backup-job execution response", method="POST", path=path)
        return body

    @staticmethod
    def _check_rejection(body: Any, *, method: str, path: str) -> None:
        if isinstance(body, dict) and body.get("success") is False:
            raise MtnCloudError("Backup operation was rejected", method=method, path=path)
