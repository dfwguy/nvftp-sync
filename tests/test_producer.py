import hashlib
import json
import subprocess

from nvis_integration.config import Limits
from nvis_integration.producer import build_envelope
from nvis_integration.security import verify_checksums


def test_build_envelope_is_self_consistent(tmp_path):
    repo = tmp_path / "source"
    subprocess.run(["git", "init", "-b", "main", repo], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.email", "test@example.invalid"], check=True)
    (repo / "README.md").write_text("release\n")
    subprocess.run(["git", "-C", repo, "add", "README.md"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", "release"], check=True, capture_output=True)
    output = tmp_path / "output"
    result = build_envelope(
        repository=repo,
        output=output,
        artifact="release_20260915",
        target="nvis-ova/tool",
        source_kind="snapshot",
        classification_attested_by="owner@example.invalid",
    )
    assert result["target"] == "nvis-ova/tool"
    checksums = verify_checksums(output, "release_20260915", Limits())
    assert len(checksums) == 3
    manifest = json.loads((output / "release_20260915.MANIFEST.json").read_text())
    assert manifest["source_commit"] == result["source_commit"]
    assert hashlib.sha256((output / "release_20260915.git.bundle").read_bytes()).hexdigest()
