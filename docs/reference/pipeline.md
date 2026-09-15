# Pipeline reference

## Accepted pipeline sources

The root workflow accepts push, schedule, web, API, and trigger pipelines. Other pipeline sources are rejected.

## GitLab-to-NVFTP jobs

| Job | Input | Output |
| --- | --- | --- |
| `build-image` | Configured Dockerfile and build context | Configured image in GitLab Container Registry |
| `export-image` | Registry image | Deterministic compressed image archive retained for seven days |
| `upload-to-nvftp` | Exported archive | Archive and SHA-256 sidecar in `NVFTP_UPLOAD_DIR`, unless the remote checksum matches |

## NVFTP-to-GitLab jobs

| Job | Purpose |
| --- | --- |
| `pull-from-nvftp` | Checks the optional manifest, then downloads `NVFTP_DOWNLOAD_DIR` when required |
| `diff-against-target-main` | Overlays the snapshot with deletion awareness and records the diff |
| `validate-candidate` | Reconstructs the pinned candidate and runs `TARGET_TEST_COMMAND` |
| `publish-sync-branch` | Commits and pushes the validated candidate branch |
| `create-or-update-mr` | Creates or updates the corresponding open merge request |

The inbound jobs retain reports for seven days:

- `changed_files.txt`
- `diff_summary.txt`
- `git_status.txt`
- `sync.env`
- `test.log`
- merge-request description and API metadata when applicable

No-change runs skip validation, publication, and MR creation while succeeding overall. Validation failures retain diagnostic artifacts and prevent publication.

The inbound manifest checkpoint uses a GitLab cache scoped to the project. It advances only in `create-or-update-mr`, after all required inbound work succeeds. A missing cache entry causes a full download, so cache eviction affects performance rather than correctness.

## Repository layout

| Path | Purpose |
| --- | --- |
| `.gitlab-ci.yml` | Workflow sources, stages, shared variables, and local includes |
| `ci/gitlab-to-nvftp.yml` | Outbound jobs and selection rules |
| `ci/nvftp-to-gitlab.yml` | Inbound jobs and selection rules |
| `scripts/common.sh` | Validation and shared SSH/configuration helpers |
| `scripts/nvftp_upload.sh` | Non-interactive outbound SFTP transfer |
| `scripts/nvftp_pull.sh` | Non-interactive recursive inbound SFTP transfer |
| `scripts/checkpoint_download_manifest.sh` | Records the manifest from a successful inbound pipeline |
| `scripts/clone_target.sh` | Authenticated target clone |
| `scripts/prepare_candidate.sh` | Deletion-aware content overlay |
| `scripts/detect_changes.sh` | Change reports and pinned-base metadata |
| `scripts/run_tests.sh` | Target validation command |
| `scripts/publish_sync_branch.sh` | Commit and guarded branch publication |
| `scripts/create_or_update_mr.sh` | Idempotent MR API operation |
| `examples/gitlab-to-nvftp-container/` | Demonstration workload; not framework code |
