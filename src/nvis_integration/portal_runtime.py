"""Composition root for the operated NVIS-OVA portal."""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import threading
import time
from collections.abc import Callable
from typing import TypeVar

from .config import Config
from .credentials import CredentialStore
from .gitlab_read import GitLabReadModel
from .health import node_health, run_probe
from .hub_api import (
    HubApplication,
    PortalReaders,
    SqlitePortalReaders,
)
from .nvftp import NvftpClient
from .portal_audit import PortalAuditLog
from .rbac import PasswordAuthenticator, SessionCodec
from .state import JobStore

T = TypeVar("T")


class _Cache:
    """Small thread-safe TTL cache for expensive external read models."""

    def __init__(self, seconds: int = 15) -> None:
        self.seconds = seconds
        self._values: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}

    def get(self, key: str, loader: Callable[[], T]) -> T:
        with self._lock:
            cached = self._values.get(key)
            if cached and time.monotonic() - cached[0] < self.seconds:
                return cached[1]  # type: ignore[return-value]
            key_lock = self._key_locks.setdefault(key, threading.Lock())
        with key_lock:
            with self._lock:
                cached = self._values.get(key)
                if cached and time.monotonic() - cached[0] < self.seconds:
                    return cached[1]  # type: ignore[return-value]
            value = loader()
            with self._lock:
                self._values[key] = (time.monotonic(), value)
            return value


def _authenticator(path: pathlib.Path) -> PasswordAuthenticator:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise ValueError("portal auth records must be a non-empty JSON object")
    records: dict[str, tuple[str, str] | tuple[str, str, str]] = {}
    for username, item in raw.items():
        if not isinstance(item, dict):
            raise TypeError("invalid portal auth record")
        role = str(item["role"])
        password_record = str(item["password_record"])
        display_name = item.get("display_name")
        records[str(username)] = (
            (role, password_record, str(display_name))
            if display_name is not None
            else (role, password_record)
        )
    return PasswordAuthenticator(records)


def bootstrap_portal(root: pathlib.Path, *, username: str = "admin") -> dict[str, pathlib.Path]:
    """Create one-time local portal credentials without printing secret material."""
    secrets_root = root / "secrets"
    secrets_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(secrets_root, 0o700)
    paths = {
        "auth_records": secrets_root / "portal-auth.json",
        "session_secret": secrets_root / "session-secret",
        "bootstrap_password": secrets_root / "bootstrap-admin-password",
    }
    if any(path.exists() for path in paths.values()):
        raise FileExistsError("portal bootstrap files already exist; refusing to overwrite")
    password = secrets.token_urlsafe(24)
    record = {
        username: {
            "role": "admin",
            "password_record": PasswordAuthenticator.password_record(password),
        }
    }
    values = {
        "auth_records": json.dumps(record, indent=2, sort_keys=True) + "\n",
        "session_secret": secrets.token_hex(48) + "\n",
        "bootstrap_password": password + "\n",
    }
    created: list[pathlib.Path] = []
    try:
        for name, path in paths.items():
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created.append(path)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(values[name])
                stream.flush()
                os.fsync(stream.fileno())
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return paths


def build_portal(
    config: Config,
    *,
    web_root: pathlib.Path,
    auth_records_file: pathlib.Path,
    session_secret_file: pathlib.Path,
    credential_root: pathlib.Path,
    secure_cookies: bool = True,
) -> HubApplication:
    """Build the secure portal with live GitLab/NVFTP and local state readers."""
    # Ensure the read-only SQLite view always has a schema, even on first boot.
    JobStore(config.paths.state / "jobs.sqlite3")
    state = SqlitePortalReaders(config.paths.state / "jobs.sqlite3")
    gitlab = GitLabReadModel(
        base_url=config.gitlab.base_url,
        group=config.gitlab.group_path,
        token_file=config.gitlab.token_file,
    )
    nvftp = NvftpClient(config.nvftp)
    cache = _Cache()

    def raw_repositories() -> list[dict[str, object]]:
        def load() -> list[dict[str, object]]:
            repositories = gitlab.repositories()
            statistics = gitlab.repository_statistics()
            return [
                {
                    **item,
                    "commit_count": statistics.get(int(item["id"]), {}).get("commit_count", "—"),
                }
                for item in repositories
            ]

        return cache.get("repositories", load)

    def raw_pipelines() -> list[dict[str, object]]:
        return cache.get("pipelines", gitlab.pipelines)

    def raw_merge_requests() -> list[dict[str, object]]:
        return cache.get("merge_requests", gitlab.merge_requests)

    def repositories() -> list[dict[str, object]]:
        merge_request_counts: dict[int, int] = {}
        for request in raw_merge_requests():
            project_id = int(request.get("project_id", 0))
            merge_request_counts[project_id] = merge_request_counts.get(project_id, 0) + 1
        return [
            {
                "name": item.get("name", "unknown"),
                "description": item.get("path_with_namespace", ""),
                "branch": item.get("default_branch") or "uninitialized",
                "commits": item.get("commit_count", "—"),
                "forks": item.get("forks_count", 0),
                "mrs": merge_request_counts.get(int(item["id"]), 0),
                "status": "healthy",
                "lang": "Git",
                "url": item.get("web_url"),
                "visibility": item.get("visibility"),
                "last_activity_at": item.get("last_activity_at"),
            }
            for item in raw_repositories()
        ]

    def pipelines() -> list[dict[str, object]]:
        return [
            {
                "id": item.get("id"),
                "name": item.get("project_name", f"project {item.get('project_id', '?')}"),
                "ref": item.get("ref", ""),
                "stage": "GitLab CI",
                "status": item.get("status", "unknown"),
                "progress": 100 if item.get("status") in {"success", "failed", "canceled"} else 50,
                "duration": "live",
                "actor": "GitLab",
                "url": item.get("web_url"),
                "sha": item.get("sha"),
            }
            for item in raw_pipelines()
        ]

    def activity() -> list[dict[str, object]]:
        return [
            {
                "who": str(item.get("actor", "system"))[:2].upper(),
                "name": item.get("actor", "system"),
                "action": item.get("event_type", "event"),
                "target": item.get("job_id", ""),
                "time": item.get("timestamp", ""),
                **item,
            }
            for item in state.activity()
        ]

    def approvals() -> list[dict[str, object]]:
        pending = [job for job in state.jobs() if job.get("status") in {"planned", "approved"}]
        return [
            {
                "title": f"Import {job.get('artifact', 'artifact')}",
                "detail": f"{job.get('source', '')} → {job.get('target', '')}",
                "risk": "Medium",
                "owner": job.get("requester", "unknown"),
                "age": job.get("created_at", ""),
                "job_id": job.get("id"),
                "status": job.get("status"),
            }
            for job in pending
        ]

    def overview() -> dict[str, object]:
        repos, pipe, merge_requests = repositories(), pipelines(), raw_merge_requests()
        return {
            "commits": sum(value for item in repos if isinstance((value := item["commits"]), int)),
            "pipelines": sum(item.get("status") in {"running", "pending"} for item in pipe),
            "merge_requests": len(merge_requests),
            "forks": sum(int(item.get("forks", 0)) for item in repos),
            "artifacts": state.summary()["jobs"],
        }

    def integrations() -> dict[str, object]:
        gitlab_probe = run_probe(gitlab.probe)
        nvftp_probe = run_probe(
            lambda: "authorized path reachable"
            if nvftp.list(config.nvftp.allowed_prefixes[0])
            else "authorized path empty"
        )
        return {
            "gitlab": gitlab_probe.__dict__,
            "nvftp": nvftp_probe.__dict__,
            "slack": {
                "status": "configured"
                if config.slack.bot_token_file.is_file() and config.slack.app_token_file.is_file()
                else "not_configured",
                "latency_ms": 0,
                "detail": "Socket Mode credentials present"
                if config.slack.bot_token_file.is_file() and config.slack.app_token_file.is_file()
                else "Slack bot and app token files are required",
            },
        }

    def health() -> dict[str, object]:
        probes = integrations()
        node = node_health(config.paths.root)
        return {
            "services": [
                {
                    "name": "GitLab integration",
                    "key": "gitlab-api-v4",
                    "status": "healthy" if probes["gitlab"]["status"] == "healthy" else "failed",  # type: ignore[index]
                    "value": f"{probes['gitlab']['latency_ms']} ms",  # type: ignore[index]
                    "label": probes["gitlab"]["detail"],  # type: ignore[index]
                    "usage": 100 if probes["gitlab"]["status"] == "healthy" else 0,  # type: ignore[index]
                },
                {
                    "name": "NVFTP integration",
                    "key": "sftp-socket-mode",
                    "status": "healthy" if probes["nvftp"]["status"] == "healthy" else "failed",  # type: ignore[index]
                    "value": f"{probes['nvftp']['latency_ms']} ms",  # type: ignore[index]
                    "label": probes["nvftp"]["detail"],  # type: ignore[index]
                    "usage": 100 if probes["nvftp"]["status"] == "healthy" else 0,  # type: ignore[index]
                },
                {
                    "name": "Slack command agent",
                    "key": "nvis-ova-slack.service",
                    "status": "healthy" if probes["slack"]["status"] == "configured" else "warning",  # type: ignore[index]
                    "value": probes["slack"]["status"],  # type: ignore[index]
                    "label": probes["slack"]["detail"],  # type: ignore[index]
                    "usage": 100 if probes["slack"]["status"] == "configured" else 0,  # type: ignore[index]
                },
                {
                    "name": "Audit store",
                    "key": "portal-audit.jsonl",
                    "status": "healthy",
                    "value": f"{audit.verify()[1]} events",
                    "label": "Hash-chain verification available",
                    "usage": 100,
                },
            ],
            "node": node,
            "integrations": probes,
        }

    readers = PortalReaders(
        summary=state.summary,
        overview=overview,
        activity=activity,
        jobs=state.jobs,
        repositories=repositories,
        pipelines=pipelines,
        merge_requests=raw_merge_requests,
        approvals=approvals,
        integrations=integrations,
        node=lambda: node_health(config.paths.root),
        health=health,
    )
    session_secret = session_secret_file.read_bytes().strip()
    audit = PortalAuditLog(config.paths.state / "portal-audit.jsonl")
    credentials = CredentialStore(
        credential_root, {"gitlab_token", "slack_bot_token", "slack_app_token"}
    )
    return HubApplication(
        web_root=web_root,
        upload_root=config.paths.inbox / "portal-uploads",
        max_upload_bytes=min(config.limits.max_artifact_bytes, 2_000_000_000),
        sessions=SessionCodec(session_secret),
        authenticator=_authenticator(auth_records_file),
        audit=audit,
        readers=readers,
        credentials=credentials,
        secure_cookies=secure_cookies,
    )
