# Configuration reference

All synchronization variables belong in the target project. The tooling
project does not need NVFTP or target-repository credentials.

## Template controls

| Variable | Default | Purpose |
| --- | --- | --- |
| `NVFTP_SYNC_PROJECT_URL` | `$CI_SERVER_URL/nvis-ova/nvftp-sync.git` | Tooling repository cloned by jobs |
| `NVFTP_SYNC_TOOLS_REF` | `main` | Tooling tag or commit; match the included template revision |
| `NVFTP_SYNC_JOB_IMAGE` | `alpine:3.20` | Alpine-compatible job image; override with a target test image when needed |
| `NVFTP_SYNC_INBOUND_ENABLED` | `false` | Enables scheduled and explicitly selected manual inbound jobs |
| `NVFTP_SYNC_OUTBOUND_ENABLED` | `false` | Enables publication after synchronized content changes on the default branch |
| `TARGET_SYNC_PATH` | `.` | Content scope; `.` reconciles the target codebase root |
| `TARGET_TEST_COMMAND` | none | Required validation command for inbound candidates |
| `SYNC_BRANCH_PREFIX` | `nvftp-sync` | Prefix for generated proposal branches |
| `SYNC_SOURCE_NAME` | download-directory basename | Human-readable source name used in branches and MRs |

## NVFTP connection

| Variable | Required | Purpose |
| --- | --- | --- |
| `NVFTP_USER` | yes | NVFTP-generated SSH username |
| `NVFTP_PRIVATE_KEY` | yes | Passwordless private key configured as a GitLab File variable |
| `NVFTP_HOST` | no | Defaults to `transfer.nvftp.nvidia.com` |
| `NVFTP_KNOWN_HOSTS` | recommended | Trusted server entry; enables strict host verification |
| `NVFTP_DOWNLOAD_DIR` | inbound | Incoming proposal directory |
| `NVFTP_UPLOAD_DIR` | outbound | Published approved-content directory |
| `NVFTP_DOWNLOAD_MANIFEST` | no | Producer-maintained manifest used to skip an unchanged download |

Use separate download and upload directories. The download directory contains
unreviewed proposals; the upload directory represents the approved default
branch.

## GitLab credentials

`GITLAB_API_TOKEN` is required for inbound operation. Store a masked, protected
target-project access token with the minimum role/scopes needed to push a
non-protected sync branch and create or update an MR (`api` and
`write_repository` in the current setup). It must not be allowed to push to the
protected default branch.

The target project also needs permission to clone the tooling project with its
`CI_JOB_TOKEN`. Add it to the tooling project's job-token allowlist.

The template derives the target path, ID, default branch, and repository URL
from `CI_PROJECT_*`; those values no longer need manual configuration.
