import hashlib
import io
import json
import pathlib
import subprocess
import tarfile

from nvis_integration.config import Config, Gitlab, Limits, Nvftp, Paths, Slack
from nvis_integration.models import ImportRequest
from nvis_integration.state import JobStore
from nvis_integration.worker import ImportWorker


def _config(tmp_path: pathlib.Path) -> Config:
    return Config(
        paths=Paths(
            root=tmp_path,
            inbox=tmp_path / "inbox",
            quarantine=tmp_path / "quarantine",
            work=tmp_path / "work",
            state=tmp_path / "state",
        ),
        nvftp=Nvftp(
            host="transfer.example.invalid",
            username="bot",
            identity_file=tmp_path / "key",
            known_hosts_file=tmp_path / "known_hosts",
            allowed_prefixes=("/nvidia-space/shared/team",),
        ),
        gitlab=Gitlab(
            base_url="https://gitlab.example.invalid",
            group_path="nvis-ova",
            group_id=1,
            bot_username="bot",
            token_file=tmp_path / "token",
            new_project_visibility="private",
        ),
        slack=Slack(
            bot_token_file=tmp_path / "slack-bot",
            app_token_file=tmp_path / "slack-app",
            allowed_user_ids=("U1",),
            approver_user_ids=("U2",),
            allowed_channel_ids=("C1",),
        ),
        limits=Limits(),
    )


def _synthetic_artifacts(destination: pathlib.Path, artifact: str) -> None:
    destination.mkdir(parents=True)
    repo = destination.parent / "synthetic-source"
    subprocess.run(["git", "init", "-b", "main", repo], check=True, capture_output=True)
    subprocess.run(["git", "-C", repo, "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", repo, "config", "user.email", "test@example.invalid"], check=True)
    (repo / "README.md").write_text("synthetic integration test\n")
    subprocess.run(["git", "-C", repo, "add", "README.md"], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", "synthetic"], check=True, capture_output=True)
    bundle = destination / f"{artifact}.git.bundle"
    subprocess.run(["git", "-C", repo, "bundle", "create", bundle, "--all"], check=True)
    manifest = destination / f"{artifact}.MANIFEST.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact": artifact,
                "target": "nvis-ova/synthetic",
                "source_kind": "change-set",
                "classification": "not_export_controlled",
                "classification_attested_by": "test-owner@example.invalid",
                "created_at": "2026-09-15T00:00:00Z",
            }
        )
    )
    tar_path = destination / f"{artifact}.tar.gz"
    with tarfile.open(tar_path, "w:gz") as archive:
        payload = b"synthetic integration test\n"
        info = tarfile.TarInfo("README.md")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    names = [manifest.name, bundle.name, tar_path.name]
    sums = "".join(
        f"{hashlib.sha256((destination / name).read_bytes()).hexdigest()}  {name}\n"
        for name in names
    )
    (destination / f"{artifact}.SHA256SUMS").write_text(sums)


def test_synthetic_worker_reaches_human_review(monkeypatch, tmp_path):
    config = _config(tmp_path)
    for path in (
        config.paths.inbox,
        config.paths.quarantine,
        config.paths.work,
        config.paths.state,
    ):
        path.mkdir()
    store = JobStore(config.paths.state / "jobs.sqlite3")
    request = ImportRequest(
        "/nvidia-space/shared/team/project", "synthetic_abc123", "nvis-ova/synthetic"
    )
    job = store.create(request, requester="U1", channel="C1", idempotency_key="test")
    store.transition(job.id, expected=("planned",), status="approved")
    worker = ImportWorker(config, store)

    def fake_download(source, artifact, destination):
        del source
        _synthetic_artifacts(destination, artifact)
        return list(destination.iterdir())

    class FakeGitlab:
        def __init__(self, _config):
            pass

        def publish_bundle(self, **kwargs):
            assert kwargs["target"] == "nvis-ova/synthetic"
            return "https://gitlab.example.invalid/nvis-ova/synthetic/-/merge_requests/1"

    monkeypatch.setattr(worker.nvftp, "download", fake_download)
    monkeypatch.setattr("nvis_integration.worker.optional_malware_scan", lambda _path: None)
    monkeypatch.setattr("nvis_integration.worker.GitlabClient", FakeGitlab)
    result = worker.run(job.id)
    assert result.endswith("/merge_requests/1")
    assert store.get(job.id).status == "succeeded"
    assert not (config.paths.work / job.id).exists()
