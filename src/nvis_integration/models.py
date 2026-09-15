"""Validated requests passed across the Slack/worker boundary."""

from __future__ import annotations

import dataclasses
import re
import shlex

_REMOTE_PATH = re.compile(r"^/[A-Za-z0-9._/-]+$")
_ARTIFACT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_PROJECT = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


@dataclasses.dataclass(frozen=True)
class ImportRequest:
    source: str
    artifact: str
    target: str


def parse_import_command(text: str, group_path: str) -> ImportRequest:
    """Parse strict key=value syntax; unknown or duplicate keys fail closed."""
    values: dict[str, str] = {}
    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        raise ValueError(f"invalid command quoting: {exc}") from exc
    for token in tokens:
        if "=" not in token:
            raise ValueError(f"expected key=value, got {token!r}")
        key, value = token.split("=", 1)
        if key not in {"nvftp", "artifact", "target"}:
            raise ValueError(f"unknown field: {key}")
        if key in values:
            raise ValueError(f"duplicate field: {key}")
        values[key] = value
    missing = {"nvftp", "artifact"} - values.keys()
    if missing:
        raise ValueError(f"missing fields: {', '.join(sorted(missing))}")
    source = values["nvftp"].rstrip("/")
    if not _REMOTE_PATH.fullmatch(source) or ".." in source.split("/"):
        raise ValueError("NVFTP path contains unsupported characters or traversal")
    artifact = values["artifact"]
    if not _ARTIFACT.fullmatch(artifact):
        raise ValueError("invalid artifact basename")
    target = values.get("target", "auto").strip("/")
    if target == "auto":
        return ImportRequest(source=source, artifact=artifact, target=target)
    prefix = f"{group_path}/"
    if not target.startswith(prefix):
        target = f"{prefix}{target}"
    project = target.removeprefix(prefix)
    if "/" in project or not _PROJECT.fullmatch(project):
        raise ValueError(f"target must be one project directly under {group_path}")
    return ImportRequest(source=source, artifact=artifact, target=target)


def ensure_allowed_source(source: str, prefixes: tuple[str, ...]) -> None:
    for prefix in prefixes:
        normalized = prefix.rstrip("/")
        if source == normalized or source.startswith(normalized + "/"):
            return
    raise PermissionError("NVFTP source is outside the configured allowlist")
