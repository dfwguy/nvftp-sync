"""Restricted SFTP client for NVIDIA NVFTP."""

from __future__ import annotations

import pathlib
import re
import subprocess

from .config import Nvftp
from .models import ensure_allowed_source

ARTIFACT_SUFFIXES = (".MANIFEST.json", ".SHA256SUMS", ".git.bundle", ".tar.gz")
_REMOTE_PATH = re.compile(r"^/[A-Za-z0-9._/-]+$")
_ARTIFACT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


def _validate_remote(source: str, artifact: str | None = None) -> None:
    if not _REMOTE_PATH.fullmatch(source) or ".." in source.split("/"):
        raise ValueError("unsafe NVFTP path")
    if artifact is not None and not _ARTIFACT.fullmatch(artifact):
        raise ValueError("unsafe artifact basename")


class NvftpClient:
    def __init__(self, config: Nvftp) -> None:
        self.config = config

    def _run(self, commands: list[str], timeout: int = 120) -> str:
        command = [
            "sftp",
            "-F",
            "/dev/null",
            "-b",
            "-",
            "-i",
            str(self.config.identity_file),
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={self.config.known_hosts_file}",
            "-o",
            "ConnectTimeout=15",
            f"{self.config.username}@{self.config.host}",
        ]
        completed = subprocess.run(
            command,
            input="\n".join([*commands, "bye", ""]),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"NVFTP operation failed: {detail[-1000:]}")
        return completed.stdout

    def list(self, source: str) -> str:
        _validate_remote(source)
        ensure_allowed_source(source, self.config.allowed_prefixes)
        return self._run([f"ls -la {source}"], timeout=40)

    def assert_artifact_set(self, source: str, artifact: str) -> None:
        _validate_remote(source, artifact)
        listing = self.list(source)
        missing = [suffix for suffix in ARTIFACT_SUFFIXES if artifact + suffix not in listing]
        if missing:
            raise FileNotFoundError(f"artifact set is incomplete; missing: {', '.join(missing)}")

    def download(self, source: str, artifact: str, destination: pathlib.Path) -> list[pathlib.Path]:
        _validate_remote(source, artifact)
        ensure_allowed_source(source, self.config.allowed_prefixes)
        destination.mkdir(parents=True, exist_ok=False)
        commands: list[str] = []
        paths: list[pathlib.Path] = []
        for suffix in ARTIFACT_SUFFIXES:
            filename = artifact + suffix
            local = destination / filename
            paths.append(local)
            commands.append(f"get {source}/{filename} {local}")
        self._run(commands, timeout=600)
        return paths
