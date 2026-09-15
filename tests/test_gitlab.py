import pathlib
import subprocess

from nvis_integration.config import Gitlab
from nvis_integration.gitlab import GitlabClient


def _commit(repo: pathlib.Path, name: str, content: str) -> str:
    (repo / name).write_text(content)
    subprocess.run(["git", "-C", repo, "add", name], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-m", name], check=True, capture_output=True)
    return subprocess.run(
        ["git", "-C", repo, "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def test_snapshot_is_applied_on_top_of_destination_history(tmp_path, monkeypatch):
    destination_source = tmp_path / "destination-source"
    incoming_source = tmp_path / "incoming-source"
    remote = tmp_path / "remote.git"
    for repo in (destination_source, incoming_source):
        subprocess.run(["git", "init", "-b", "main", repo], check=True, capture_output=True)
        subprocess.run(["git", "-C", repo, "config", "user.name", "Test"], check=True)
        subprocess.run(
            ["git", "-C", repo, "config", "user.email", "test@example.invalid"], check=True
        )
    base = _commit(destination_source, "old.txt", "old\n")
    incoming = _commit(incoming_source, "new.txt", "new\n")
    bundle = tmp_path / "incoming.bundle"
    subprocess.run(
        ["git", "-C", incoming_source, "bundle", "create", bundle, "--all"], check=True
    )
    subprocess.run(["git", "init", "--bare", "-b", "main", remote], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", destination_source, "push", str(remote), "main"],
        check=True,
        capture_output=True,
    )
    token = tmp_path / "token"
    token.write_text("test-token-value-not-real")
    client = GitlabClient(
        Gitlab(
            base_url="https://gitlab.example.invalid",
            group_path="nvis-ova",
            group_id=1,
            bot_username="bot",
            token_file=token,
            new_project_visibility="private",
        )
    )
    monkeypatch.setattr(
        client,
        "get_project",
        lambda _target: {
            "id": 1,
            "http_url_to_repo": str(remote),
            "web_url": "https://gitlab.example.invalid/nvis-ova/tool",
            "default_branch": "main",
        },
    )

    def fake_api(method, endpoint, payload=None):
        del payload
        if method == "GET" and "merge_requests?" in endpoint:
            return 200, []
        return 201, {"web_url": "https://gitlab.example.invalid/nvis-ova/tool/-/merge_requests/1"}

    monkeypatch.setattr(client, "_api", fake_api)
    work = tmp_path / "work"
    work.mkdir()
    result = client.publish_bundle(
        target="nvis-ova/tool",
        bundle=bundle,
        incoming_oid=incoming,
        artifact="release",
        work_directory=work,
        source_kind="snapshot",
    )
    assert result.endswith("/merge_requests/1")
    branch = "refs/heads/nvftp/"
    refs = subprocess.run(
        ["git", "-C", remote, "for-each-ref", "--format=%(refname) %(objectname)", branch],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip().split()
    published = refs[-1]
    parent = subprocess.run(
        ["git", "-C", remote, "rev-parse", f"{published}^"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    assert parent == base
    published_tree = subprocess.run(
        ["git", "-C", remote, "rev-parse", f"{published}^{{tree}}"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    incoming_tree = subprocess.run(
        ["git", "-C", incoming_source, "rev-parse", "HEAD^{tree}"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    assert published_tree == incoming_tree
