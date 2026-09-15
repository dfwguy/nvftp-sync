from __future__ import annotations

import json
import os
import pathlib

import pytest

from nvis_integration.portal_audit import PortalAuditLog


def test_portal_audit_is_private_hash_chained_and_detects_tampering(tmp_path: pathlib.Path) -> None:
    audit = PortalAuditLog(tmp_path / "audit" / "portal.jsonl")
    audit("auth.login", "alice", {})
    audit("upload.staged", "alice", {"upload_id": "abc", "bytes": 5})
    assert audit.verify() == (True, 2)
    assert os.stat(audit.path).st_mode & 0o777 == 0o600
    records = [json.loads(line) for line in audit.path.read_text().splitlines()]
    assert records[1]["previous_hash"] == records[0]["hash"]
    records[0]["actor"] = "mallory"
    audit.path.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    assert audit.verify() == (False, 1)


def test_portal_audit_rejects_secret_shaped_details(tmp_path: pathlib.Path) -> None:
    audit = PortalAuditLog(tmp_path / "portal.jsonl")
    with pytest.raises(ValueError, match="secret-like"):
        audit("credential.rotated", "admin", {"gitlab_token": "must-not-log"})
    assert not audit.path.exists()
