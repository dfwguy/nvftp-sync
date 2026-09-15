"""One-job-at-a-time trusted ingestion worker."""

from __future__ import annotations

import shutil

from .config import Config
from .gitlab import GitlabClient
from .manifest import load_manifest
from .nvftp import NvftpClient
from .security import (
    inspect_git_bundle_secrets,
    inspect_tarball,
    optional_malware_scan,
    verify_checksums,
    verify_git_bundle,
    verify_snapshot_equivalence,
)
from .state import Job, JobStore


class ImportWorker:
    def __init__(self, config: Config, store: JobStore) -> None:
        self.config = config
        self.store = store
        self.nvftp = NvftpClient(config.nvftp)

    def plan(self, job: Job) -> None:
        self.nvftp.assert_artifact_set(job.source, job.artifact)

    def run(self, job_id: str) -> str:
        job = self.store.transition(job_id, expected=("approved",), status="running")
        inbox = self.config.paths.inbox / job.id
        work = self.config.paths.work / job.id
        work.mkdir(parents=True, exist_ok=False)
        try:
            self.nvftp.download(job.source, job.artifact, inbox)
            verify_checksums(inbox, job.artifact, self.config.limits)
            manifest = load_manifest(
                inbox / f"{job.artifact}.MANIFEST.json",
                artifact=job.artifact,
                target=job.target,
            )
            findings = inspect_tarball(inbox / f"{job.artifact}.tar.gz", self.config.limits)
            findings.extend(
                inspect_git_bundle_secrets(
                    inbox / f"{job.artifact}.git.bundle", self.config.limits
                )
            )
            verify_snapshot_equivalence(
                inbox / f"{job.artifact}.tar.gz",
                inbox / f"{job.artifact}.git.bundle",
                self.config.limits,
            )
            if findings:
                raise ValueError(
                    f"potential secrets found: {', '.join(sorted(set(findings))[:20])}"
                )
            optional_malware_scan(inbox)
            incoming_oid, _refs = verify_git_bundle(inbox / f"{job.artifact}.git.bundle")
            gitlab = GitlabClient(self.config.gitlab)
            result_url = gitlab.publish_bundle(
                target=job.target,
                bundle=inbox / f"{job.artifact}.git.bundle",
                incoming_oid=incoming_oid,
                artifact=job.artifact,
                work_directory=work,
                source_kind=manifest.source_kind,
                base_commit=manifest.base_commit,
            )
            self.store.transition(
                job.id, expected=("running",), status="succeeded", result_url=result_url
            )
            return result_url
        except Exception as exc:
            if inbox.exists():
                quarantine = self.config.paths.quarantine / job.id
                if not quarantine.exists():
                    shutil.move(str(inbox), quarantine)
            self.store.transition(
                job.id,
                expected=("running",),
                status="failed",
                error=str(exc)[:1000],
            )
            raise
        finally:
            shutil.rmtree(work, ignore_errors=True)
