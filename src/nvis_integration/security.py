"""Artifact integrity and passive security inspection."""

from __future__ import annotations

import hashlib
import pathlib
import re
import subprocess
import tarfile
import tempfile

from .config import Limits
from .nvftp import ARTIFACT_SUFFIXES

_HASH_LINE = re.compile(r"^([0-9a-fA-F]{64})\s+\*?([^/\\]+)$")
_SECRET_PATTERNS = {
    "private-key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "slack-token": re.compile(rb"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "aws-access-key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "gitlab-token": re.compile(rb"glpat-[A-Za-z0-9_-]{20,}"),
}


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksums(directory: pathlib.Path, artifact: str, limits: Limits) -> dict[str, str]:
    expected_names = {artifact + suffix for suffix in ARTIFACT_SUFFIXES if suffix != ".SHA256SUMS"}
    checksum_file = directory / f"{artifact}.SHA256SUMS"
    entries: dict[str, str] = {}
    for raw_line in checksum_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _HASH_LINE.fullmatch(line)
        if not match:
            raise ValueError(f"malformed checksum line: {line[:80]}")
        digest, name = match.groups()
        if name in entries:
            raise ValueError(f"duplicate checksum entry: {name}")
        entries[name] = digest.lower()
    if set(entries) != expected_names:
        raise ValueError(
            f"checksum names differ from required artifact set: {sorted(set(entries) ^ expected_names)}"
        )
    for name, expected in entries.items():
        path = directory / name
        if path.stat().st_size > limits.max_artifact_bytes:
            raise ValueError(f"artifact exceeds size limit: {name}")
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"checksum mismatch: {name}")
    return entries


def inspect_tarball(path: pathlib.Path, limits: Limits) -> list[str]:
    findings: list[str] = []
    members = 0
    unpacked = 0
    with tarfile.open(path, mode="r:gz") as archive:
        for member in archive:
            members += 1
            unpacked += member.size
            pure = pathlib.PurePosixPath(member.name)
            if pure.is_absolute() or ".." in pure.parts:
                raise ValueError(f"unsafe archive path: {member.name}")
            if member.isdev() or member.islnk():
                raise ValueError(f"unsupported archive entry: {member.name}")
            if member.issym():
                _safe_symlink_target(member.name, member.linkname)
            if members > limits.max_archive_members:
                raise ValueError("archive member limit exceeded")
            if unpacked > limits.max_unpacked_bytes:
                raise ValueError("archive expansion limit exceeded")
            if not member.isfile() or member.size > limits.max_scan_file_bytes:
                continue
            stream = archive.extractfile(member)
            if stream is None:
                continue
            payload = stream.read(limits.max_scan_file_bytes + 1)
            for label, pattern in _SECRET_PATTERNS.items():
                if pattern.search(payload):
                    findings.append(f"{label}:{member.name}")
    return sorted(set(findings))


def _safe_symlink_target(name: str, target: str) -> None:
    link = pathlib.PurePosixPath(target)
    if link.is_absolute():
        raise ValueError(f"unsafe archive symlink: {name}")
    depth = len(pathlib.PurePosixPath(name).parent.parts)
    for part in link.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            depth -= 1
        else:
            depth += 1
        if depth < 1:
            raise ValueError(f"unsafe archive symlink: {name}")


def verify_snapshot_equivalence(
    tar_path: pathlib.Path, bundle_path: pathlib.Path, limits: Limits
) -> None:
    """Require the tar snapshot and preferred bundle tree to contain identical entries."""
    incoming_oid, _ = verify_git_bundle(bundle_path)
    tar_entries: dict[str, tuple[str, str]] = {}
    with tarfile.open(tar_path, mode="r:gz") as archive:
        members = [member for member in archive if not member.isdir()]
        roots = {pathlib.PurePosixPath(member.name).parts[0] for member in members}
        strip_root = len(roots) == 1 and all(
            len(pathlib.PurePosixPath(member.name).parts) > 1 for member in members
        )
        for member in members:
            parts = pathlib.PurePosixPath(member.name).parts
            name = pathlib.PurePosixPath(*parts[1:] if strip_root else parts).as_posix()
            if member.issym():
                _safe_symlink_target(member.name, member.linkname)
                tar_entries[name] = ("120000", hashlib.sha256(member.linkname.encode()).hexdigest())
                continue
            if not member.isfile():
                raise ValueError(f"unsupported archive entry: {member.name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"could not read archive entry: {member.name}")
            mode = "100755" if member.mode & 0o111 else "100644"
            digest = hashlib.sha256()
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
            tar_entries[name] = (mode, digest.hexdigest())

    git_entries: dict[str, tuple[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="nvis-tree-compare-") as raw:
        repository = pathlib.Path(raw) / "mirror.git"
        subprocess.run(
            ["git", "clone", "--mirror", str(bundle_path), str(repository)],
            check=True,
            capture_output=True,
            timeout=180,
        )
        listing = subprocess.run(
            ["git", "-C", str(repository), "ls-tree", "-rz", "--full-tree", incoming_oid],
            check=True,
            capture_output=True,
            timeout=60,
        ).stdout
        records = [record for record in listing.split(b"\0") if record]
        if len(records) > limits.max_archive_members:
            raise ValueError("Git tree entry limit exceeded")
        for record in records:
            header, name_bytes = record.split(b"\t", 1)
            mode, object_type, oid = header.decode("ascii").split()
            if object_type != "blob" or mode not in {"100644", "100755", "120000"}:
                raise ValueError(f"unsupported Git tree entry: {name_bytes!r}")
            payload = subprocess.run(
                ["git", "-C", str(repository), "cat-file", "blob", oid],
                check=True,
                capture_output=True,
                timeout=30,
            ).stdout
            name = name_bytes.decode("utf-8", errors="surrogateescape")
            git_entries[name] = (mode, hashlib.sha256(payload).hexdigest())

    differences = sorted(
        name
        for name in set(tar_entries) | set(git_entries)
        if tar_entries.get(name) != git_entries.get(name)
    )
    if differences:
        raise ValueError(
            "tar snapshot and Git bundle trees differ: " + ", ".join(differences[:20])
        )


def inspect_git_bundle_secrets(path: pathlib.Path, limits: Limits) -> list[str]:
    """Scan every reachable, reasonably-sized blob without checking out or executing it."""
    findings: list[str] = []
    scanned_bytes = 0
    with tempfile.TemporaryDirectory(prefix="nvis-bundle-scan-") as raw:
        repository = pathlib.Path(raw) / "mirror.git"
        clone = subprocess.run(
            ["git", "clone", "--mirror", str(path), str(repository)],
            text=True,
            capture_output=True,
            check=False,
            timeout=180,
        )
        if clone.returncode != 0:
            raise ValueError(f"could not materialize Git bundle: {clone.stderr[-1000:]}")
        objects = subprocess.run(
            ["git", "-C", str(repository), "rev-list", "--objects", "--all"],
            text=True,
            capture_output=True,
            check=True,
            timeout=180,
        ).stdout.splitlines()
        if len(objects) > limits.max_archive_members:
            raise ValueError("Git object count exceeds inspection limit")
        seen: set[str] = set()
        for line in objects:
            oid, _, name = line.partition(" ")
            if oid in seen:
                continue
            seen.add(oid)
            object_type = subprocess.run(
                ["git", "-C", str(repository), "cat-file", "-t", oid],
                text=True,
                capture_output=True,
                check=True,
                timeout=10,
            ).stdout.strip()
            if object_type != "blob":
                continue
            size = int(
                subprocess.run(
                    ["git", "-C", str(repository), "cat-file", "-s", oid],
                    text=True,
                    capture_output=True,
                    check=True,
                    timeout=10,
                ).stdout
            )
            scanned_bytes += size
            if scanned_bytes > limits.max_unpacked_bytes:
                raise ValueError("Git history expansion exceeds inspection limit")
            if size > limits.max_scan_file_bytes:
                continue
            payload = subprocess.run(
                ["git", "-C", str(repository), "cat-file", "blob", oid],
                capture_output=True,
                check=True,
                timeout=30,
            ).stdout
            for label, pattern in _SECRET_PATTERNS.items():
                if pattern.search(payload):
                    findings.append(f"{label}:{name or oid}")
    return sorted(set(findings))


def verify_git_bundle(path: pathlib.Path) -> tuple[str, list[str]]:
    with tempfile.TemporaryDirectory(prefix="nvis-bundle-") as raw:
        repository = pathlib.Path(raw) / "verify.git"
        subprocess.run(["git", "init", "--bare", str(repository)], check=True, capture_output=True)
        verify = subprocess.run(
            ["git", "-C", str(repository), "bundle", "verify", str(path)],
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        if verify.returncode != 0:
            raise ValueError(f"invalid Git bundle: {(verify.stderr or verify.stdout)[-1000:]}")
        heads = subprocess.run(
            ["git", "bundle", "list-heads", str(path)],
            text=True,
            capture_output=True,
            check=True,
            timeout=60,
        ).stdout.splitlines()
    parsed = [(line.split(maxsplit=1)[0], line.split(maxsplit=1)[1]) for line in heads if " " in line]
    preferred = next((oid for oid, ref in parsed if ref == "HEAD"), None)
    preferred = preferred or next((oid for oid, ref in parsed if ref == "refs/heads/main"), None)
    preferred = preferred or next((oid for oid, ref in parsed if ref == "refs/heads/master"), None)
    if preferred is None:
        branches = [(oid, ref) for oid, ref in parsed if ref.startswith("refs/heads/")]
        if len(branches) != 1:
            raise ValueError("bundle has no unambiguous default branch")
        preferred = branches[0][0]
    return preferred, [ref for _, ref in parsed]


def optional_malware_scan(directory: pathlib.Path) -> None:
    scanner = pathlib.Path("/usr/bin/clamscan")
    if not scanner.exists():
        return
    completed = subprocess.run(
        [str(scanner), "--recursive", "--infected", "--no-summary", str(directory)],
        text=True,
        capture_output=True,
        check=False,
        timeout=600,
    )
    if completed.returncode == 1:
        raise ValueError("malware scanner reported an infected artifact")
    if completed.returncode > 1:
        raise RuntimeError(f"malware scanner failed: {completed.stderr[-1000:]}")
