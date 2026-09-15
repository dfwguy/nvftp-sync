"""Configuration loading with secrets kept in separate files."""

from __future__ import annotations

import dataclasses
import pathlib
import tomllib
from typing import Any


@dataclasses.dataclass(frozen=True)
class Paths:
    root: pathlib.Path
    inbox: pathlib.Path
    quarantine: pathlib.Path
    work: pathlib.Path
    state: pathlib.Path


@dataclasses.dataclass(frozen=True)
class Nvftp:
    host: str
    username: str
    identity_file: pathlib.Path
    known_hosts_file: pathlib.Path
    allowed_prefixes: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Gitlab:
    base_url: str
    group_path: str
    group_id: int
    bot_username: str
    token_file: pathlib.Path
    new_project_visibility: str


@dataclasses.dataclass(frozen=True)
class Slack:
    bot_token_file: pathlib.Path
    app_token_file: pathlib.Path
    allowed_user_ids: tuple[str, ...]
    approver_user_ids: tuple[str, ...]
    allowed_channel_ids: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Limits:
    max_artifact_bytes: int = 2_000_000_000
    max_archive_members: int = 100_000
    max_unpacked_bytes: int = 8_000_000_000
    max_scan_file_bytes: int = 2_000_000


@dataclasses.dataclass(frozen=True)
class Routing:
    exact_sources: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class Config:
    paths: Paths
    nvftp: Nvftp
    gitlab: Gitlab
    slack: Slack
    limits: Limits
    routing: Routing = dataclasses.field(default_factory=Routing)


def _path(value: Any, field: str) -> pathlib.Path:
    if not isinstance(value, str) or not value.startswith("/"):
        raise ValueError(f"{field} must be an absolute path")
    return pathlib.Path(value)


def _strings(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a list of strings")
    return tuple(value)


def load_config(path: pathlib.Path) -> Config:
    """Load and validate the service TOML file."""
    with path.open("rb") as stream:
        raw = tomllib.load(stream)

    paths = raw["paths"]
    nvftp = raw["nvftp"]
    gitlab = raw["gitlab"]
    slack = raw["slack"]
    limits = raw.get("limits", {})
    routing = raw.get("routing", {})
    cfg = Config(
        paths=Paths(
            root=_path(paths["root"], "paths.root"),
            inbox=_path(paths["inbox"], "paths.inbox"),
            quarantine=_path(paths["quarantine"], "paths.quarantine"),
            work=_path(paths["work"], "paths.work"),
            state=_path(paths["state"], "paths.state"),
        ),
        nvftp=Nvftp(
            host=str(nvftp["host"]),
            username=str(nvftp["username"]),
            identity_file=_path(nvftp["identity_file"], "nvftp.identity_file"),
            known_hosts_file=_path(nvftp["known_hosts_file"], "nvftp.known_hosts_file"),
            allowed_prefixes=_strings(nvftp["allowed_prefixes"], "nvftp.allowed_prefixes"),
        ),
        gitlab=Gitlab(
            base_url=str(gitlab["base_url"]).rstrip("/"),
            group_path=str(gitlab["group_path"]).strip("/"),
            group_id=int(gitlab["group_id"]),
            bot_username=str(gitlab["bot_username"]),
            token_file=_path(gitlab["token_file"], "gitlab.token_file"),
            new_project_visibility=str(gitlab.get("new_project_visibility", "private")),
        ),
        slack=Slack(
            bot_token_file=_path(slack["bot_token_file"], "slack.bot_token_file"),
            app_token_file=_path(slack["app_token_file"], "slack.app_token_file"),
            allowed_user_ids=_strings(slack["allowed_user_ids"], "slack.allowed_user_ids"),
            approver_user_ids=_strings(slack["approver_user_ids"], "slack.approver_user_ids"),
            allowed_channel_ids=_strings(slack["allowed_channel_ids"], "slack.allowed_channel_ids"),
        ),
        limits=Limits(**{key: int(value) for key, value in limits.items()}),
        routing=Routing(
            exact_sources={
                str(source).rstrip("/"): str(target).strip("/")
                for source, target in routing.get("exact_sources", {}).items()
            }
        ),
    )
    validate_config(cfg)
    return cfg


def validate_config(cfg: Config) -> None:
    if not cfg.nvftp.allowed_prefixes:
        raise ValueError("at least one NVFTP prefix must be allowed")
    if cfg.gitlab.new_project_visibility not in {"private", "internal"}:
        raise ValueError("new projects must use private or internal visibility")
    for prefix in cfg.nvftp.allowed_prefixes:
        if not prefix.startswith("/") or ".." in prefix.split("/"):
            raise ValueError(f"unsafe NVFTP prefix: {prefix}")
    target_prefix = f"{cfg.gitlab.group_path}/"
    for source, target in cfg.routing.exact_sources.items():
        if not source.startswith("/") or ".." in source.split("/"):
            raise ValueError(f"unsafe routing source: {source}")
        project = target.removeprefix(target_prefix)
        if not target.startswith(target_prefix) or "/" in project or not project:
            raise ValueError(f"routing target must be directly under {cfg.gitlab.group_path}: {target}")
    if not cfg.gitlab.base_url.startswith("https://"):
        raise ValueError("GitLab must use HTTPS")


def read_secret(path: pathlib.Path) -> str:
    """Read a non-empty secret without ever logging its contents."""
    value = path.read_text(encoding="utf-8").strip()
    if not value or value.startswith("REPLACE_"):
        raise RuntimeError(f"credential is not configured: {path}")
    return value
