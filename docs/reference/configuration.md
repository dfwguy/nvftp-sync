# Configuration reference

## Pipeline selection

| Variable | Default | Accepted values | Purpose |
| --- | --- | --- | --- |
| `SYNC_DIRECTION` | `gitlab-to-nvftp` | `gitlab-to-nvftp`, `nvftp-to-gitlab`, `both` | Selects which jobs are added to the pipeline |

## Shared NVFTP variables

| Variable | Required | Type | Purpose |
| --- | --- | --- | --- |
| `NVFTP_USER` | Yes | Variable | NVFTP-generated SSH username |
| `NVFTP_PRIVATE_KEY` | Yes | **File** | Dedicated passwordless private key |
| `NVFTP_HOST` | No | Variable | SFTP host; defaults to `transfer.nvftp.nvidia.com` |
| `NVFTP_KNOWN_HOSTS` | No | Variable or File | Trusted host entry; enables strict host verification |
| `NVFTP_REMOTE_DIR` | Deprecated | Variable | Compatibility fallback for either direction-specific directory |

Without `NVFTP_KNOWN_HOSTS`, the scripts use OpenSSH's `accept-new` policy. With it, they use strict checking against the supplied entry.

## GitLab-to-NVFTP variables

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `NVFTP_UPLOAD_DIR` | Yes | — | Remote directory receiving the image archive |
| `OUTBOUND_BUILD_CONTEXT` | No | `examples/gitlab-to-nvftp-container` | Docker build context |
| `OUTBOUND_DOCKERFILE` | No | `examples/gitlab-to-nvftp-container/Dockerfile` | Dockerfile path relative to the repository root |
| `OUTBOUND_IMAGE_TAG` | No | `$CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA` | Registry image built and exported by the pipeline |
| `OUTBOUND_ARCHIVE_NAME` | No | `container-image.tar.gz` | Artifact name and remote upload filename |
| `OUTBOUND_FORCE_UPLOAD` | No | `false` | Set to `true` to upload even when the remote checksum matches |

The defaults exercise the foundation repository's example. A production NVIS OVA repository normally sets `OUTBOUND_BUILD_CONTEXT=.` and points `OUTBOUND_DOCKERFILE` at its own Dockerfile.

## NVFTP-to-GitLab variables

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `NVFTP_DOWNLOAD_DIR` | Yes | — | Remote folder downloaded recursively |
| `NVFTP_DOWNLOAD_MANIFEST` | No | unset | Remote manifest used to skip an unchanged recursive download |
| `GITLAB_API_TOKEN` | Yes | — | Token for target clone, branch push, and MR API calls |
| `TARGET_PROJECT_PATH` | Yes | — | Target `namespace/project` path |
| `TARGET_PROJECT_ID` | Yes | — | Numeric target GitLab project ID |
| `TARGET_TEST_COMMAND` | Yes | — | Validation command run from the target repository root |
| `TARGET_DEFAULT_BRANCH` | No | `main` | Comparison base and MR target |
| `TARGET_SYNC_PATH` | No | `synced-content` | Repository-relative path mirrored from NVFTP |
| `TARGET_REPO_URL` | No | Derived | Override target clone/push URL |
| `TARGET_GITLAB_API_URL` | No | `CI_API_V4_URL` | Override target GitLab API base URL |
| `SYNC_BRANCH_PREFIX` | No | `nvftp-sync` | Prefix for deterministic proposal branches |
| `SYNC_SOURCE_NAME` | No | Download-folder basename | Label used in branch and MR metadata |
| `GITLAB_SYNC_USER_NAME` | No | `NVFTP Sync Bot` | Commit author name |
| `GITLAB_SYNC_USER_EMAIL` | No | `nvftp-sync@noreply.invalid` | Commit author email |

`TARGET_SYNC_PATH` must be a safe repository-relative subdirectory. Root paths, `.git`, and parent traversal are rejected.

The token user needs repository read/write access and API access in the target project. Keep the default branch protected and do not grant permission to bypass its rules.

When `NVFTP_DOWNLOAD_MANIFEST` is set, the producer must update that remote file whenever any synchronized content changes and only after the content upload completes. The pipeline checkpoints its checksum only after the entire inbound workflow succeeds.
