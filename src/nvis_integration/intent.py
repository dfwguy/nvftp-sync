"""Fail-closed parsing for the Slack control surface.

Slack text is untrusted input.  This module turns a small, documented language into
typed values; callers must never pass the original text to a shell or API.
"""

from __future__ import annotations

import dataclasses
import enum
import re
import shlex

from .models import ImportRequest, parse_import_command


class Operation(enum.StrEnum):
    IMPORT = "import"
    BRANCH = "branch"
    STATUS = "status"
    HELP = "help"
    CANCEL = "cancel"
    REPLAY = "replay"


@dataclasses.dataclass(frozen=True)
class SlackIntent:
    operation: Operation
    request: ImportRequest | None = None
    job_id: str | None = None
    project: str | None = None
    branch: str | None = None
    base: str | None = None

    @property
    def writes_externally(self) -> bool:
        return self.operation in {Operation.IMPORT, Operation.BRANCH, Operation.REPLAY}


_JOB_ID = re.compile(r"^[a-f0-9]{32}$")
_PROJECT = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_REF = re.compile(r"^(?![./])(?!.*(?:\.\.|//|@\{|\\|[~^:?*\[]))[A-Za-z0-9._/-]{1,200}(?<![./])$")
_MENTION = re.compile(r"^\s*<@[A-Z0-9]+>\s*[:,]?\s*", re.IGNORECASE)


def parse_intent(text: str, group_path: str, *, legacy_import: bool = False) -> SlackIntent:
    """Parse slash-command or constrained conversational text into a typed intent."""
    clean = _MENTION.sub("", text, count=1).strip()
    if legacy_import:
        return SlackIntent(Operation.IMPORT, request=parse_import_command(clean, group_path))
    if not clean:
        return SlackIntent(Operation.HELP)

    natural = _parse_natural(clean, group_path)
    if natural is not None:
        return natural

    try:
        tokens = shlex.split(clean)
    except ValueError as exc:
        raise ValueError(f"invalid command quoting: {exc}") from exc
    if not tokens:
        return SlackIntent(Operation.HELP)
    verb = tokens.pop(0).lower().replace("_", "-")
    if verb in {"help", "commands"}:
        _require_no_args(tokens, verb)
        return SlackIntent(Operation.HELP)
    if verb in {"import", "stage", "check-in", "checkin"}:
        return SlackIntent(
            Operation.IMPORT,
            request=parse_import_command(
                " ".join(shlex.quote(item) for item in tokens), group_path
            ),
        )
    if verb in {"status", "cancel", "replay"}:
        values = _key_values(tokens, allowed={"job"})
        job_id = values.get("job")
        if verb != "status" and job_id is None:
            raise ValueError(f"{verb} requires job=<32-character job id>")
        if job_id is not None and not _JOB_ID.fullmatch(job_id):
            raise ValueError("job must be a 32-character lowercase hexadecimal id")
        return SlackIntent(Operation(verb), job_id=job_id)
    if verb in {"branch", "fork"}:
        values = _key_values(tokens, allowed={"project", "name", "base"})
        missing = {"project", "name"} - values.keys()
        if missing:
            raise ValueError(f"branch requires fields: {', '.join(sorted(missing))}")
        project = _project(values["project"], group_path)
        branch = _ref(values["name"], "branch")
        base = _ref(values.get("base", "main"), "base")
        return SlackIntent(Operation.BRANCH, project=project, branch=branch, base=base)
    raise ValueError(f"unknown operation: {verb}; try `help`")


def _parse_natural(text: str, group_path: str) -> SlackIntent | None:
    flags = re.IGNORECASE
    match = re.fullmatch(
        r"(?:please\s+)?(?:import|stage|check[ -]?in)\s+(?P<artifact>[A-Za-z0-9][A-Za-z0-9._-]{0,199})"
        r"\s+from\s+(?P<source>/[A-Za-z0-9._/-]+)\s+(?:in)?to\s+(?P<target>[A-Za-z0-9._/-]+)",
        text,
        flags,
    )
    if match:
        command = f"nvftp={match['source']} artifact={match['artifact']} target={match['target']}"
        return SlackIntent(Operation.IMPORT, request=parse_import_command(command, group_path))
    match = re.fullmatch(
        r"(?:show\s+)?status(?:\s+(?:of\s+)?(?:job\s+)?)?([a-f0-9]{32})?", text, flags
    )
    if match:
        return SlackIntent(Operation.STATUS, job_id=match.group(1))
    match = re.fullmatch(r"(?:please\s+)?(cancel|replay)(?:\s+job)?\s+([a-f0-9]{32})", text, flags)
    if match:
        return SlackIntent(Operation(match.group(1).lower()), job_id=match.group(2))
    match = re.fullmatch(
        r"(?:please\s+)?(?:create\s+)?(?:branch|fork)\s+(\S+)\s+(?:in|for)\s+(\S+)"
        r"(?:\s+from\s+(\S+))?",
        text,
        flags,
    )
    if match:
        return SlackIntent(
            Operation.BRANCH,
            project=_project(match.group(2), group_path),
            branch=_ref(match.group(1), "branch"),
            base=_ref(match.group(3) or "main", "base"),
        )
    if re.fullmatch(r"(?:show\s+)?(?:help|commands)", text, flags):
        return SlackIntent(Operation.HELP)
    return None


def _key_values(tokens: list[str], *, allowed: set[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            raise ValueError(f"expected key=value, got {token!r}")
        key, value = token.split("=", 1)
        if key not in allowed:
            raise ValueError(f"unknown field: {key}")
        if key in values:
            raise ValueError(f"duplicate field: {key}")
        if not value:
            raise ValueError(f"empty field: {key}")
        values[key] = value
    return values


def _project(value: str, group_path: str) -> str:
    value = value.strip("/")
    prefix = f"{group_path}/"
    project = value.removeprefix(prefix)
    if "/" in project or not _PROJECT.fullmatch(project):
        raise ValueError(f"project must be directly under {group_path}")
    return f"{prefix}{project}"


def _ref(value: str, field: str) -> str:
    if not _REF.fullmatch(value) or value.endswith(".lock"):
        raise ValueError(f"invalid Git {field} name")
    return value


def _require_no_args(tokens: list[str], verb: str) -> None:
    if tokens:
        raise ValueError(f"{verb} takes no arguments")
