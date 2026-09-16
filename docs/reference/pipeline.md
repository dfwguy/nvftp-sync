# Pipeline reference

## Tooling repository

The root pipeline only runs shell tests. It has no transfer jobs, secrets, or
content publication behavior.

## Target repository

Including `ci/target-sync.yml` adds two jobs:

| Job | Trigger | Result |
| --- | --- | --- |
| `nvftp-sync-inbound` | Schedule on the default branch, or an explicitly selected manual pipeline | Validates NVFTP input and creates/updates a target MR |
| `nvftp-sync-outbound` | Push to the default branch | Mirrors the approved codebase to NVFTP |

Inbound is a single fail-fast transaction: pull, deletion-aware overlay,
change detection, target validation, guarded branch publication, and MR
creation/update. A failed validation cannot publish a branch or MR.

Outbound uses an SFTP-backed `lftp mirror --reverse --delete`; files removed
from Git are removed from the published NVFTP directory. It writes
`.nvftp-sync-manifest` only after the mirror succeeds.

When synchronizing the repository root, `.git/`, `.gitlab-ci.yml`, and
`.nvftp-sync-runtime/` are protected control paths and are excluded in both
directions.

Both jobs use the same project-scoped GitLab `resource_group`, preventing an
inbound and outbound operation for the same target from running concurrently.
Reports are retained as job artifacts for seven days.
