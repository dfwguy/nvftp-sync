import json

import pytest

from nvis_integration.manifest import load_manifest


def _write(tmp_path, **updates):
    payload = {
        "schema_version": 1,
        "artifact": "release",
        "target": "nvis-ova/rack-status-pythoncm",
        "source_kind": "snapshot",
        "classification": "not_export_controlled",
        "classification_attested_by": "owner@example.invalid",
        "created_at": "2026-09-15T00:00:00Z",
    }
    payload.update(updates)
    path = tmp_path / "release.MANIFEST.json"
    path.write_text(json.dumps(payload))
    return path


def test_manifest_accepts_human_attested_non_export_controlled_artifact(tmp_path):
    manifest = load_manifest(
        _write(tmp_path), artifact="release", target="nvis-ova/rack-status-pythoncm"
    )
    assert manifest.source_kind == "snapshot"


@pytest.mark.parametrize("classification", ["unknown", "export_controlled", ""])
def test_manifest_blocks_unapproved_classification(tmp_path, classification):
    with pytest.raises(PermissionError, match="classification"):
        load_manifest(
            _write(tmp_path, classification=classification),
            artifact="release",
            target="nvis-ova/rack-status-pythoncm",
        )
