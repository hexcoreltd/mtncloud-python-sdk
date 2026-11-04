"""Modern service for configured backups and backup executions."""

from typing import Any, List

from mtn_cloud.models.backup import Backup, BackupJob, BackupResult
from mtn_cloud.modern_exceptions import MtnCloudError
from mtn_cloud.services.base import Page, Service


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
        params = {"max": limit, "offset": offset, "phrase": phrase}
        return self._list_page(
            params={key: value for key, value in params.items() if value is not None}
        )

    def list(self, **kwargs: Any) -> List[Backup]:
        return self.list_page(**kwargs).items

    def get(self, backup_id: int) -> Backup:
        return self._get(backup_id)

    def delete(self, backup_id: int) -> bool:
        self._core.request("DELETE", f"{self.path}/{backup_id}")
        return True

    def execute(self, backup_id: int) -> dict[str, Any]:
        """Trigger an immediate execution of a configured backup."""

        body = self._core.request("POST", f"{self.path}/{backup_id}/execute")
        if not isinstance(body, dict):
            raise MtnCloudError("Invalid backup execution response")
        return body

    def list_results(self, backup_id: int, *, limit: int | None = None) -> List[BackupResult]:
        body = self._core.request(
            "GET",
            f"{self.path}/{backup_id}/results",
            params={"max": limit} if limit is not None else None,
        )
        if not isinstance(body, dict) or not isinstance(body.get("results"), list):
            raise MtnCloudError("Invalid backup-result response")
        return [BackupResult.model_validate(item) for item in body["results"]]

    def list_jobs(self, *, limit: int | None = None, offset: int = 0) -> List[BackupJob]:
        body = self._core.request(
            "GET",
            f"{self.path}/jobs",
            params={"max": limit, "offset": offset},
        )
        if not isinstance(body, dict) or not isinstance(body.get("jobs"), list):
            raise MtnCloudError("Invalid backup-job response")
        return [BackupJob.model_validate(item) for item in body["jobs"]]

    def get_job(self, job_id: int) -> BackupJob:
        body = self._core.request("GET", f"{self.path}/jobs/{job_id}")
        if not isinstance(body, dict):
            raise MtnCloudError("Invalid backup-job response")
        return BackupJob.model_validate(body.get("job", body))

    def execute_job(self, job_id: int) -> dict[str, Any]:
        body = self._core.request("POST", f"{self.path}/jobs/{job_id}/execute")
        if not isinstance(body, dict):
            raise MtnCloudError("Invalid backup-job execution response")
        return body
