import hashlib
import io
import pathlib
import subprocess
import tarfile

import pytest

from nvis_integration.config import Limits
from nvis_integration.security import (
    inspect_git_bundle_secrets,
    inspect_tarball,
    verify_checksums,
    verify_git_bundle,
    verify_snapshot_equivalence,
)


def _tar(path: pathlib.Path, name: str, payload: bytes) -> None:
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo(name)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))


def test_tar_rejects_traversal(tmp_path):
    path = tmp_path / "bad.tar.gz"
    _tar(path, "../escape", b"bad")
    with pytest.raises(ValueError, match="unsafe archive path"):
        inspect_tarball(path, Limits())


def test_tar_reports_private_key(tmp_path):
    path = tmp_path / "secret.tar.gz"
    _tar(path, "secret.txt", b"-----BEGIN OPENSSH PRIVATE KEY-----")
    assert inspect_tarball(path, Limits()) == ["private-key:secret.txt"]


def test_checksum_set_is_exact(tmp_path):
    artifact = "sample"
    files = {
        f"{artifact}.MANIFEST.json": b"manifest",
        f"{artifact}.git.bundle": b"bundle",
        f"{artifact}.tar.gz": b"archive",
    }
    for name, payload in files.items():
        (tmp_path / name).write_bytes(payload)
    sums = "".join(f"{hashlib.sha256(payload).hexdigest()}  {name}\n" for name, payload in files.items())
    (tmp_path / f"{artifact}.SHA256SUMS").write_text(sums)
    assert verify_checksums(tmp_path, artifact, Limits()).keys() == files.keys()


def test_real_git_bundle_verifies(tmp_path):
    repo = tmp_path / "source"
    subprocess.run(["git", "init", "-b", "main", repo], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.email", "test@example.invalid"], check=True)
    (repo / "README.md").write_text("synthetic\n")
    subprocess.run(["git", "-C", repo, "add", "README.md"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", "synthetic"], check=True, capture_output=True)
    bundle = tmp_path / "source.bundle"
    subprocess.run(["git", "-C", repo, "bundle", "create", bundle, "--all"], check=True)
    oid, refs = verify_git_bundle(bundle)
    assert len(oid) == 40
    assert "refs/heads/main" in refs


def test_git_history_secret_is_detected(tmp_path):
    repo = tmp_path / "source-secret"
    subprocess.run(["git", "init", "-b", "main", repo], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.email", "test@example.invalid"], check=True)
    secret = repo / "deleted-secret.txt"
    secret.write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nnot-real")
    subprocess.run(["git", "-C", repo, "add", secret.name], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", "add secret"], check=True, capture_output=True)
    secret.unlink()
    subprocess.run(["git", "-C", repo, "add", "-u"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", "remove secret"], check=True, capture_output=True)
    bundle = tmp_path / "secret.bundle"
    subprocess.run(["git", "-C", repo, "bundle", "create", bundle, "--all"], check=True)
    assert inspect_git_bundle_secrets(bundle, Limits()) == [
        "private-key:deleted-secret.txt"
    ]


def test_snapshot_and_bundle_must_describe_same_tree(tmp_path):
    repo = tmp_path / "source"
    subprocess.run(["git", "init", "-b", "main", repo], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.email", "test@example.invalid"], check=True)
    (repo / "README.md").write_text("same\n")
    subprocess.run(["git", "-C", repo, "add", "README.md"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", "same"], check=True, capture_output=True)
    bundle = tmp_path / "source.bundle"
    subprocess.run(["git", "-C", repo, "bundle", "create", bundle, "--all"], check=True)
    matching = tmp_path / "matching.tar.gz"
    _tar(matching, "release/README.md", b"same\n")
    verify_snapshot_equivalence(matching, bundle, Limits())
    different = tmp_path / "different.tar.gz"
    _tar(different, "release/README.md", b"different\n")
    with pytest.raises(ValueError, match="trees differ"):
        verify_snapshot_equivalence(different, bundle, Limits())


def test_tar_allows_relative_in_tree_symlink(tmp_path):
    path = tmp_path / "links.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        payload = b"instructions\n"
        regular = tarfile.TarInfo("release/AGENTS.md")
        regular.size = len(payload)
        archive.addfile(regular, io.BytesIO(payload))
        link = tarfile.TarInfo("release/CLAUDE.md")
        link.type = tarfile.SYMTYPE
        link.linkname = "AGENTS.md"
        archive.addfile(link)
    assert inspect_tarball(path, Limits()) == []
