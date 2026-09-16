# Reviewed NVFTP synchronization for GitLab

This repository contains reusable GitLab CI configuration and scripts. It does
not contain synchronized product content and its own pipeline never reads from
or writes to NVFTP.

A target repository includes [`ci/target-sync.yml`](ci/target-sync.yml). The
jobs then execute in that target project:

```text
NVFTP incoming folder
        |
        | scheduled target pipeline
        v
target sync branch and merge request
        |
        | human review and merge
        v
target default branch
        |
        | default-branch push pipeline
        v
NVFTP published folder
```

The target default branch is the source of truth. NVFTP input is treated as a
proposal until its merge request is approved and merged.

## Adopt the template

Add this to the target repository's `.gitlab-ci.yml`:

```yaml
include:
  - project: nvis-ova/nvftp-sync
    ref: <release-tag>
    file: /ci/target-sync.yml

variables:
  NVFTP_SYNC_TOOLS_REF: "<release-tag>"
  NVFTP_SYNC_INBOUND_ENABLED: "true"
  NVFTP_SYNC_OUTBOUND_ENABLED: "true"
  TARGET_SYNC_PATH: "."
  TARGET_TEST_COMMAND: "<target validation command>"
```

Pin the include and `NVFTP_SYNC_TOOLS_REF` to the same release tag. The jobs
clone the scripts from that revision with `CI_JOB_TOKEN`; the tooling project
must allow the target project in its job-token allowlist.

Configure these protected CI/CD variables in the **target project**:

| Variable | Purpose |
| --- | --- |
| `NVFTP_USER` | NVFTP-generated SSH username |
| `NVFTP_PRIVATE_KEY` | Passwordless private key stored as a GitLab File variable |
| `NVFTP_KNOWN_HOSTS` | Audited host-key entry (recommended) |
| `NVFTP_DOWNLOAD_DIR` | NVFTP incoming/proposal directory |
| `NVFTP_UPLOAD_DIR` | NVFTP published/approved directory |
| `GITLAB_API_TOKEN` | Target-project token with API and repository-write access |

Use different download and upload directories. This prevents unreviewed input
from being mistaken for the approved published state.

## Automation

Create a pipeline schedule in the target project on its protected default
branch. No schedule variable is required: when
`NVFTP_SYNC_INBOUND_ENABLED=true`, scheduled default-branch pipelines run the
inbound reconciliation job. For a one-off test, start a manual pipeline on the
default branch; no selector variable is required.

Inbound behavior:

1. Recursively download `NVFTP_DOWNLOAD_DIR`.
2. Reconcile it against the repository root, including deletions.
3. Run `TARGET_TEST_COMMAND` against the candidate working tree.
4. Push or refresh a deterministic sync branch.
5. Create or update an MR in the target repository.

Outbound behavior:

1. Run only after a push to the target default branch.
2. Mirror the approved codebase to `NVFTP_UPLOAD_DIR`, including remote
   deletions.
3. Write `.nvftp-sync-manifest` last so consumers can identify a completed
   publication and its exact Git commit.

The two jobs share a project-scoped `resource_group`, so they cannot operate on
the workspace concurrently.

Root synchronization protects `.git/`, `.gitlab-ci.yml`, and
`.nvftp-sync-runtime/`. These control/runtime paths are neither imported from
nor published to NVFTP.

## Local verification

```sh
./scripts/run_tests.sh
```

See [`docs/reference/configuration.md`](docs/reference/configuration.md) for the
full variable reference and
[`docs/how-to/adopt-in-an-nvis-ova-repository.md`](docs/how-to/adopt-in-an-nvis-ova-repository.md)
for rollout steps.
