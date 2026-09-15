"""Versioned artifact provenance and GitLab-publication policy."""

from __future__ import annotations

import dataclasses
import json
import pathlib
import re

_OID = re.compile(r"^[0-9a-f]{40}$")


@dataclasses.dataclass(frozen=True)
class ArtifactManifest:
    schema_version: int
    artifact: str
    target: str
    source_kind: str
    classification: str
    classification_attested_by: str
    created_at: str
    base_commit: str | None = None


def load_manifest(path: pathlib.Path, *, artifact: str, target: str) -> ArtifactManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid artifact manifest: {exc}") from exc
    if not isinstance(raw, dict):
        raise TypeError("artifact manifest must be a JSON object")
    required = {
        "schema_version",
        "artifact",
        "target",
        "source_kind",
        "classification",
        "classification_attested_by",
        "created_at",
    }
    missing = required - raw.keys()
    if missing:
        raise ValueError(f"artifact manifest is missing: {', '.join(sorted(missing))}")
    manifest = ArtifactManifest(
        schema_version=int(raw["schema_version"]),
        artifact=str(raw["artifact"]),
        target=str(raw["target"]),
        source_kind=str(raw["source_kind"]),
        classification=str(raw["classification"]),
        classification_attested_by=str(raw["classification_attested_by"]),
        created_at=str(raw["created_at"]),
        base_commit=str(raw["base_commit"]) if raw.get("base_commit") else None,
    )
    if manifest.schema_version != 1:
        raise ValueError(f"unsupported artifact manifest version: {manifest.schema_version}")
    if manifest.artifact != artifact:
        raise ValueError("manifest artifact does not match the requested artifact")
    if manifest.target != target:
        raise ValueError("manifest target does not match the approved GitLab target")
    if manifest.source_kind not in {"snapshot", "change-set", "evidence"}:
        raise ValueError(f"unsupported source_kind: {manifest.source_kind}")
    if manifest.classification != "not_export_controlled":
        raise PermissionError(
            "GitLab publication requires classification=not_export_controlled"
        )
    if not manifest.classification_attested_by.strip():
        raise ValueError("classification_attested_by must name the responsible human")
    if manifest.base_commit is not None and not _OID.fullmatch(manifest.base_commit):
        raise ValueError("base_commit must be a full lowercase Git object ID")
    return manifest
