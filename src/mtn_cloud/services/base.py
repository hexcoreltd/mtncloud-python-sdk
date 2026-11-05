"""Shared primitives for modern service clients."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Generic, TypeVar, cast

from pydantic import BaseModel

from mtn_cloud.core import CoreClient
from mtn_cloud.modern_exceptions import AmbiguousLookupError, LookupNotFoundError, MtnCloudError

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    """A typed page returned by a list operation."""

    items: list[T]
    offset: int = 0
    limit: int | None = None
    total: int | None = None

    @property
    def has_more(self) -> bool:
        return self.total is not None and self.offset + len(self.items) < self.total


class Service(Generic[T]):
    """Base class for services backed by a collection endpoint."""

    path: str
    item_key: str
    list_key: str
    model: type[T]

    def __init__(self, core: CoreClient) -> None:
        self._core = core

    def _list_page(self, *, params: dict[str, Any] | None = None) -> Page[T]:
        body = self._core.request("GET", self.path, params=params)
        if not isinstance(body, Mapping):
            raise MtnCloudError(f"Invalid response from {self.path}: expected an object")
        if body.get("success") is False:
            raise MtnCloudError("Collection request was rejected", method="GET", path=self.path)

        raw_items = body.get(self.list_key)
        if not isinstance(raw_items, list):
            raise MtnCloudError(
                f"Invalid response from {self.path}: expected '{self.list_key}' to be a list"
            )

        meta = body.get("meta")
        meta = meta if isinstance(meta, Mapping) else {}
        requested = params or {}
        offset = (
            self._integer(
                meta.get("offset"), default=self._integer(requested.get("offset"), default=0)
            )
            or 0
        )
        limit = self._integer(meta.get("max"))
        if limit is None:
            limit = self._integer(meta.get("limit"), default=self._integer(requested.get("max")))
        total = self._integer(meta.get("total"))
        # Morpheus `size` counts this page, not the full collection. Without
        # `total`, traversal must use page fullness rather than stop at `size`.
        return Page(
            items=[self.model.model_validate(item) for item in raw_items],
            offset=offset,
            limit=limit,
            total=total,
        )

    def list_all(self, *, page_size: int = 100, **filters: Any) -> list[T]:
        """Follow collection pages, failing on detected overlap or offset mismatches."""
        if type(page_size) is not int or page_size < 1:
            raise ValueError("page_size must be a positive integer")
        list_page = cast(Callable[..., Page[T]], getattr(self, "list_page"))  # noqa: B009
        collected: list[T] = []
        seen_ids: set[int] = set()
        offset = 0
        while True:
            page = list_page(limit=page_size, offset=offset, **filters)
            if not page.items:
                break
            if page.offset != offset:
                raise MtnCloudError(
                    "Collection pagination returned an unexpected offset",
                    method="GET",
                    path=self.path,
                )
            page_ids: set[int] = set()
            for item in page.items:
                item_id = getattr(item, "id", None)
                if type(item_id) is int:
                    if item_id in seen_ids:
                        raise MtnCloudError(
                            "Collection pagination repeated resource IDs",
                            method="GET",
                            path=self.path,
                        )
                    page_ids.add(item_id)
            seen_ids.update(page_ids)
            collected.extend(page.items)
            offset += len(page.items)
            if page.total is not None:
                if len(collected) >= page.total:
                    break
            elif len(page.items) < min(page_size, page.limit or page_size):
                break
        return collected

    def _get(self, resource_id: int) -> T:
        body = self._core.request("GET", f"{self.path}/{resource_id}")
        if not isinstance(body, Mapping):
            raise MtnCloudError(f"Invalid response from {self.path}/{resource_id}")
        if body.get("success") is False:
            raise MtnCloudError(
                "Resource request was rejected", method="GET", path=f"{self.path}/{resource_id}"
            )
        payload = body.get(self.item_key, body)
        if not isinstance(payload, Mapping):
            raise MtnCloudError(f"Invalid '{self.item_key}' response from {self.path}")
        return self.model.model_validate(payload)

    @staticmethod
    def _integer(value: Any, *, default: int | None = None) -> int | None:
        return value if type(value) is int and value >= 0 else default

    def _get_by_name(self, kind: str, name: str, **filters: Any) -> T:
        """Return the single resource whose name exactly matches ``name``."""

        candidates = self.list_all(name=name, **filters)
        matches = [item for item in candidates if getattr(item, "name", None) == name]
        if not matches:
            raise LookupNotFoundError(f"{kind} '{name}' was not found")
        if len(matches) > 1:
            ids = sorted(cast(Any, item).id for item in matches)
            raise AmbiguousLookupError(f"{kind} name '{name}' is ambiguous: ids {ids}")
        return matches[0]
