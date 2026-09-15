"""Append-only, hash-chained audit sink for portal-level actions."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import pathlib
import re
import time
from collections.abc import Mapping

_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,159}$")
_SENSITIVE_KEYS = {"secret", "password", "token", "authorization", "cookie", "value"}


class PortalAuditLog:
    """Synchronous audit hook that fails closed on corrupt or unsafe input."""

    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)

    def __call__(self, event: str, actor: str, details: Mapping[str, object]) -> None:
        if not _LABEL.fullmatch(event) or not _LABEL.fullmatch(actor):
            raise ValueError("invalid audit label")
        _reject_sensitive_keys(details)
        descriptor = os.open(self.path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "a+", encoding="utf-8") as stream:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                stream.seek(0)
                records = [line for line in stream.read().splitlines() if line]
                previous = "0" * 64
                sequence = 1
                if records:
                    last = json.loads(records[-1])
                    previous = str(last["hash"])
                    sequence = int(last["sequence"]) + 1
                record: dict[str, object] = {
                    "sequence": sequence,
                    "timestamp": time.time_ns(),
                    "event": event,
                    "actor": actor,
                    "details": dict(details),
                    "previous_hash": previous,
                }
                record["hash"] = _hash(record)
                stream.seek(0, os.SEEK_END)
                stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            # fdopen owns the descriptor except when it failed before entering.
            try:
                os.close(descriptor)
            except OSError:
                pass

    def verify(self) -> tuple[bool, int]:
        if not self.path.exists():
            return True, 0
        previous = "0" * 64
        count = 0
        with self.path.open(encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_SH)
            for count, line in enumerate(stream, 1):
                try:
                    record = json.loads(line)
                    supplied = record.pop("hash")
                    if record["previous_hash"] != previous or supplied != _hash(record):
                        return False, count
                    previous = supplied
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    return False, count
        return True, count


def _hash(record: Mapping[str, object]) -> str:
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _reject_sensitive_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(part in _SENSITIVE_KEYS for part in normalized.split("_")):
                raise ValueError("secret-like values are forbidden in audit details")
            _reject_sensitive_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_sensitive_keys(item)
