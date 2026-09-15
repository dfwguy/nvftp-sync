"""Minimal GitLab API and Git publisher with token redaction."""

from __future__ import annotations

import base64
import datetime as dt
import json
import pathlib
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from .config import Gitlab, read_secret


class GitlabClient:
    def __init__(self, config: Gitlab) -> None:
        self.config = config
        self.token = read_secret(config.token_file)
        if not config.bot_username or config.bot_username == "REPLACE_GITLAB_BOT_USERNAME":
            raise RuntimeError("GitLab bot username is not configured")

    def _api(
        self, method: str, endpoint: str, payload: dict[str, object] | None = None
    ) -> tuple[int, object]:
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            f"{self.config.base_url}/api/v4/{endpoint.lstrip('/')}",
            data=body,
            method=method,
            headers={
                "PRIVATE-TOKEN": self.token,
                "Content-Type": "application/json",
                "User-Agent": "nvis-integration/0.1",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            detail = raw.decode(errors="replace")[-1000:]
            if exc.code == 404:
                return 404, {}
            raise RuntimeError(
                f"GitLab API {method} {endpoint} failed ({exc.code}): {detail}"
            ) from exc

    def get_project(self, target: str) -> dict[str, object] | None:
        status, response = self._api("GET", f"projects/{urllib.parse.quote(target, safe='')}")
        return None if status == 404 else dict(response)  # type: ignore[arg-type]

    def create_project(self, target: str) -> dict[str, object]:
        project_path = target.split("/", 1)[1]
        _, response = self._api(
            "POST",
            "projects",
            {
                "name": project_path,
                "path": project_path,
                "namespace_id": self.config.group_id,
                "visibility": self.config.new_project_visibility,
                "initialize_with_readme": False,
                "only_allow_merge_if_pipeline_succeeds": True,
                "only_allow_merge_if_all_discussions_are_resolved": True,
                "remove_source_branch_after_merge": True,
            },
        )
        return dict(response)  # type: ignore[arg-type]

    def create_branch(self, *, target: str, branch: str, ref: str) -> str:
        """Create a non-protected feature branch without force or destructive options."""
        project = self.get_project(target)
        if project is None:
            raise ValueError(f"GitLab project does not exist: {target}")
        default_branch = str(project.get("default_branch") or "main")
        protected = {default_branch, "main", "master", "develop", "development", "release"}
        if branch in protected or branch.startswith(("release/", "hotfix/", "nvftp/")):
            raise ValueError("refusing to create a protected or integration-reserved branch")
        project_id = int(project["id"])
        self._api(
            "POST",
            f"projects/{project_id}/repository/branches",
            {"branch": branch, "ref": ref},
        )
        return f"{project['web_url']}/-/tree/{urllib.parse.quote(branch, safe='/')}"

    def _git_env(self) -> dict[str, str]:
        import os

        encoded = base64.b64encode(f"{self.config.bot_username}:{self.token}".encode()).decode()
        env = dict(os.environ)
        env.update(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "http.extraHeader",
                "GIT_CONFIG_VALUE_0": f"Authorization: Basic {encoded}",
                "GIT_TERMINAL_PROMPT": "0",
            }
        )
        return env

    def _git(self, arguments: list[str], cwd: pathlib.Path | None = None) -> str:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            env=self._git_env(),
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).replace(self.token, "[REDACTED]")
            raise RuntimeError(f"Git operation failed: {detail[-1500:]}")
        return completed.stdout

    def publish_bundle(
        self,
        *,
        target: str,
        bundle: pathlib.Path,
        incoming_oid: str,
        artifact: str,
        work_directory: pathlib.Path,
        source_kind: str = "change-set",
        base_commit: str | None = None,
    ) -> str:
        project = self.get_project(target)
        created = project is None
        if created:
            project = self.create_project(target)
        assert project is not None
        http_url = str(project["http_url_to_repo"])
        web_url = str(project["web_url"])
        short = incoming_oid[:12]
        if created:
            bare = work_directory / "new-project.git"
            self._git(["init", "--bare", str(bare)])
            self._git(["-C", str(bare), "fetch", str(bundle), incoming_oid])
            self._git(["-C", str(bare), "remote", "add", "origin", http_url])
            self._git(["-C", str(bare), "push", "origin", f"{incoming_oid}:refs/heads/main"])
            return web_url

        checkout = work_directory / "repository"
        self._git(["clone", "--no-checkout", http_url, str(checkout)])
        default_branch = str(project.get("default_branch") or "main")
        self._git(["fetch", str(bundle), incoming_oid], cwd=checkout)
        current_tip = self._git(["rev-parse", f"origin/{default_branch}"], cwd=checkout).strip()
        if base_commit and source_kind == "change-set" and base_commit != current_tip:
            raise RuntimeError(
                "change-set base_commit is stale; regenerate it from the current default branch"
            )
        common = subprocess.run(
            ["git", "merge-base", f"origin/{default_branch}", incoming_oid],
            cwd=checkout,
            text=True,
            capture_output=True,
            check=False,
        )
        if common.returncode != 0 and source_kind != "snapshot":
            raise RuntimeError("incoming bundle has no common history with the existing repository")
        date = dt.datetime.now(dt.UTC).strftime("%Y%m%d")
        branch = f"nvftp/{date}-{short}"
        publish_oid = incoming_oid
        if source_kind == "snapshot":
            self._git(["checkout", "-B", branch, f"origin/{default_branch}"], cwd=checkout)
            self._git(["read-tree", "--reset", "-u", incoming_oid], cwd=checkout)
            changed = subprocess.run(
                ["git", "diff", "--quiet", "--cached", f"origin/{default_branch}"],
                cwd=checkout,
                check=False,
            ).returncode
            if changed == 0:
                return web_url
            self._git(["config", "user.name", "NVIS Integration Bot"], cwd=checkout)
            self._git(["config", "user.email", "nvis-integration@nvidia.com"], cwd=checkout)
            self._git(
                [
                    "commit",
                    "-m",
                    f"Import verified NVFTP snapshot {artifact}",
                    "-m",
                    f"NVFTP-Incoming-Commit: {incoming_oid}",
                    "-m",
                    f"NVFTP-Base-Commit: {current_tip}",
                ],
                cwd=checkout,
            )
            publish_oid = self._git(["rev-parse", "HEAD"], cwd=checkout).strip()
        self._git(["push", "origin", f"{publish_oid}:refs/heads/{branch}"], cwd=checkout)
        project_id = int(project["id"])
        query = urllib.parse.urlencode(
            {"state": "opened", "source_branch": branch, "target_branch": default_branch}
        )
        _, existing = self._api("GET", f"projects/{project_id}/merge_requests?{query}")
        if isinstance(existing, list) and existing:
            return str(existing[0]["web_url"])
        _, mr = self._api(
            "POST",
            f"projects/{project_id}/merge_requests",
            {
                "source_branch": branch,
                "target_branch": default_branch,
                "title": f"Import verified NVFTP artifact {artifact}",
                "description": (
                    f"Automated import of `{artifact}` after checksum, archive, secret, "
                    f"malware, and Git bundle validation. Source kind: `{source_kind}`. "
                    f"Incoming commit: `{incoming_oid}`. Integration base: `{current_tip}`."
                    "\n\nHuman approval is required; "
                    "the integration bot does not approve or merge."
                ),
                "remove_source_branch": True,
            },
        )
        return str(mr["web_url"])  # type: ignore[index]
