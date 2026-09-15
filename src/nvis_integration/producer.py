"""Create a deterministic, self-contained artifact envelope from a trusted Git checkout."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re
import subprocess

from .config import Limits
from .security import verify_snapshot_equivalence

_ARTIFACT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_TARGET = re.compile(r"^[a-z0-9][a-z0-9._-]+/[a-z0-9][a-z0-9._-]+$")
_OID = re.compile(r"^[0-9a-f]{40}$")


def build_envelope(
    *,
    repository: pathlib.Path,
    output: pathlib.Path,
    artifact: str,
    target: str,
    source_kind: str,
    classification_attested_by: str,
    base_commit: str | None = None,
) -> dict[str, object]:
    if not _ARTIFACT.fullmatch(artifact):
        raise ValueError("invalid artifact basename")
    if not _TARGET.fullmatch(target):
        raise ValueError("target must be a direct group/project path")
    if source_kind not in {"snapshot", "change-set"}:
        raise ValueError("source_kind must be snapshot or change-set")
    if not classification_attested_by.strip():
        raise ValueError("classification_attested_by is required")
    if source_kind == "change-set" and not base_commit:
        raise ValueError("change-set artifacts require base_commit")
    if base_commit and not _OID.fullmatch(base_commit):
        raise ValueError("base_commit must be a full lowercase Git object ID")
    if not (repository / ".git").exists():
        raise ValueError(f"not a Git checkout: {repository}")
    status = _git(repository, "status", "--porcelain=v1", "--untracked-files=all")
    if status.strip():
        raise ValueError("repository must be clean before packaging")
    commit = _git(repository, "rev-parse", "HEAD").strip()
    if base_commit:
        ancestor = subprocess.run(
            ["git", "-C", str(repository), "merge-base", "--is-ancestor", base_commit, commit],
            check=False,
        )
        if ancestor.returncode != 0:
            raise ValueError("base_commit is not an ancestor of HEAD")
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "manifest": output / f"{artifact}.MANIFEST.json",
        "checksums": output / f"{artifact}.SHA256SUMS",
        "bundle": output / f"{artifact}.git.bundle",
        "tar": output / f"{artifact}.tar.gz",
    }
    existing = [path.name for path in paths.values() if path.exists()]
    if existing:
        raise FileExistsError(f"refusing to replace existing envelope files: {existing}")
    subprocess.run(
        ["git", "-C", str(repository), "bundle", "create", str(paths["bundle"]), "HEAD"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "archive",
            "--format=tar.gz",
            f"--prefix={artifact}/",
            f"--output={paths['tar']}",
            "HEAD",
        ],
        check=True,
        capture_output=True,
    )
    manifest = {
        "schema_version": 1,
        "artifact": artifact,
        "target": target,
        "source_kind": source_kind,
        "classification": "not_export_controlled",
        "classification_attested_by": classification_attested_by,
        "created_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "base_commit": base_commit,
        "source_commit": commit,
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    checksum_names = (paths["manifest"], paths["bundle"], paths["tar"])
    paths["checksums"].write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in checksum_names)
    )
    verify_snapshot_equivalence(paths["tar"], paths["bundle"], Limits())
    return {
        "artifact": artifact,
        "source_commit": commit,
        "target": target,
        "files": {name: str(path) for name, path in paths.items()},
    }


def _git(repository: pathlib.Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        text=True,
        capture_output=True,
        timeout=120,
    )
    return completed.stdout


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
