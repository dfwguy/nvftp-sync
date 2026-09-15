"""Safe storage and rotation of the portal's named credentials."""

from __future__ import annotations

import os
import pathlib
import re
import tempfile

_NAME = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


class CredentialStore:
    """Atomic mode-0600 credential files with an explicit name allowlist."""

    def __init__(self, root: pathlib.Path, allowed_names: set[str] | frozenset[str]) -> None:
        self.root = root
        self.allowed_names = frozenset(allowed_names)
        if any(not _NAME.fullmatch(name) for name in self.allowed_names):
            raise ValueError("invalid credential name in allowlist")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(root, 0o700)

    def path(self, name: str) -> pathlib.Path:
        if name not in self.allowed_names:
            raise KeyError(name)
        return self.root / name

    def configured(self) -> dict[str, bool]:
        return {name: self.path(name).is_file() for name in sorted(self.allowed_names)}

    def rotate(self, name: str, value: str) -> None:
        target = self.path(name)
        if not value or value != value.strip() or "\0" in value or "\n" in value or "\r" in value:
            raise ValueError("credential must be a non-empty, single-line value")
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.", dir=self.root)
        temporary = pathlib.Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(value + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            os.chmod(target, 0o600)
            directory_fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)
