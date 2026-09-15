"""Allowlisted, read-only GitLab data source for the portal."""

from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .config import read_secret


class GitLabReadModel:
    """Fetch bounded group status without exposing token or unbounded API content."""

    def __init__(
        self,
        *,
        base_url: str,
        group: str,
        token_file: pathlib.Path,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("GitLab API requires HTTPS")
        self.base_url = base_url.rstrip("/")
        self.group = group.strip("/")
        self.token_file = token_file
        self._opener = opener

    def repositories(self) -> list[dict[str, object]]:
        data = self._get(
            f"groups/{urllib.parse.quote(self.group, safe='')}/projects",
            {
                "per_page": "100",
                "order_by": "last_activity_at",
                "sort": "desc",
                "include_subgroups": "true",
                "with_shared": "false",
            },
        )
        return [
            _select(
                item,
                "id",
                "name",
                "path_with_namespace",
                "web_url",
                "default_branch",
                "visibility",
                "last_activity_at",
                "open_issues_count",
                "forks_count",
            )
            for item in data
            if isinstance(item, dict)
        ]

    def repository_statistics(self) -> dict[int, dict[str, object]]:
        """Return bounded per-project statistics when the caller has access."""
        projects = self.repositories()[:50]

        def fetch(project: dict[str, object]) -> tuple[int, dict[str, object]]:
            project_id = int(project["id"])
            data = self._get(f"projects/{project_id}", {"statistics": "true"})
            if not isinstance(data, dict):
                raise TypeError("unexpected GitLab project response")
            statistics = data.get("statistics")
            return project_id, dict(statistics) if isinstance(statistics, dict) else {}

        result: dict[int, dict[str, object]] = {}
        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="gitlab-stats") as executor:
            futures = [executor.submit(fetch, project) for project in projects]
            for future in as_completed(futures):
                try:
                    project_id, statistics = future.result()
                    result[project_id] = statistics
                except (OSError, ValueError, urllib.error.URLError):
                    continue
        return result

    def pipelines(self) -> list[dict[str, object]]:
        # GitLab does not expose a group-pipelines endpoint on all deployed
        # versions. Fan out bounded, read-only project queries instead.
        projects = self.repositories()[:50]

        def fetch(project: dict[str, object]) -> list[dict[str, object]]:
            project_id = int(project["id"])
            data = self._get(
                f"projects/{project_id}/pipelines",
                {"per_page": "5", "order_by": "updated_at", "sort": "desc"},
            )
            return [
                {
                    **_select(
                        item,
                        "id",
                        "iid",
                        "project_id",
                        "status",
                        "ref",
                        "sha",
                        "web_url",
                        "updated_at",
                    ),
                    "project_name": project.get("name", str(project_id)),
                }
                for item in data
                if isinstance(item, dict)
            ]

        pipelines: list[dict[str, object]] = []
        failures = 0
        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="gitlab-read") as executor:
            futures = [executor.submit(fetch, project) for project in projects]
            for future in as_completed(futures):
                try:
                    pipelines.extend(future.result())
                except (OSError, ValueError, urllib.error.URLError):
                    failures += 1
        if projects and failures == len(projects):
            raise RuntimeError("all GitLab project pipeline queries failed")
        pipelines.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return pipelines[:100]

    def merge_requests(self) -> list[dict[str, object]]:
        data = self._get(
            f"groups/{urllib.parse.quote(self.group, safe='')}/merge_requests",
            {"per_page": "100", "state": "opened", "order_by": "updated_at", "sort": "desc"},
        )
        return [
            _select(
                item,
                "id",
                "iid",
                "project_id",
                "title",
                "state",
                "draft",
                "web_url",
                "source_branch",
                "target_branch",
                "updated_at",
                "merge_status",
            )
            for item in data
            if isinstance(item, dict)
        ]

    def probe(self) -> str:
        data = self._get(f"groups/{urllib.parse.quote(self.group, safe='')}", {})
        if not isinstance(data, dict) or "id" not in data:
            raise RuntimeError("unexpected GitLab health response")
        return "authenticated and group reachable"

    def _get(self, endpoint: str, query: dict[str, str]) -> object:
        url = f"{self.base_url}/api/v4/{endpoint}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "PRIVATE-TOKEN": read_secret(self.token_file),
                "Accept": "application/json",
                "User-Agent": "nvis-ova-hub/0.1",
            },
        )
        with self._opener(request, timeout=10) as response:
            # Bound response size independently of a potentially false Content-Length.
            raw = response.read(4_000_001)
        if len(raw) > 4_000_000:
            raise RuntimeError("GitLab response exceeded portal limit")
        return json.loads(raw)


def _select(source: dict[str, object], *fields: str) -> dict[str, object]:
    return {field: source[field] for field in fields if field in source}
