# Bidirectional GitLab and NVFTP synchronization

This repository is the foundation for consistent GitLab and NVFTP transfer processes across NVIS OVA repositories. It hosts two selectable GitLab pipelines on one branch:

- `gitlab-to-nvftp` builds the configured container, exports it, and uploads the archive to NVFTP.
- `nvftp-to-gitlab` downloads an NVFTP folder, validates it against a separate target repository, and opens or updates a merge request.
- `both` runs both independent workflows in the same pipeline.

The default is `gitlab-to-nvftp`, which preserves the behavior of ordinary push pipelines. Choose a different value for `SYNC_DIRECTION` when starting a manual, scheduled, API, or trigger pipeline.

> [!WARNING]
> **Every Git push currently starts the GitLab → NVFTP workflow.** Because `gitlab-to-nvftp` is the default direction, pushing any branch creates a pipeline that builds, exports, and uploads a container archive when the required credentials are available. This includes documentation-only and feature-branch pushes. Confirm `NVFTP_UPLOAD_DIR` and the outbound build variables before pushing changes to a repository that uses this foundation.
>
> NVFTP → GitLab does **not** currently run on every push. It runs only when `SYNC_DIRECTION=nvftp-to-gitlab` or `both` is supplied, commonly by a manual pipeline, API/trigger request, or pipeline schedule. Creating such a schedule makes inbound synchronization automatic at that schedule's frequency and should be communicated to repository users just as prominently.

The outbound pipeline still builds and exports on every push, but it compares the archive SHA-256 with NVFTP and skips the upload when the remote checksum matches. Inbound pipelines can skip the recursive download when a producer-maintained manifest is configured. See [Avoid redundant transfers](docs/how-to/avoid-redundant-transfers.md) for the guarantees and setup requirements.

## Trigger behavior

| Trigger | Behavior without an override |
| --- | --- |
| Push to any branch | Runs GitLab → NVFTP |
| Manual web pipeline | Presents `SYNC_DIRECTION`; defaults to GitLab → NVFTP |
| API or trigger pipeline | Defaults to GitLab → NVFTP unless the request supplies `SYNC_DIRECTION` |
| Pipeline schedule | Defaults to GitLab → NVFTP unless the schedule explicitly sets `SYNC_DIRECTION` |

To run an inbound schedule, explicitly set `SYNC_DIRECTION=nvftp-to-gitlab`. To prevent push-triggered uploads, the root `workflow: rules` must be changed; merely omitting `NVFTP_UPLOAD_DIR` causes a failed outbound job rather than disabling it.

## Documentation

The documentation follows the [Diátaxis](https://diataxis.fr/) organization:

### Tutorials

- [Run your first GitLab-to-NVFTP sync](docs/tutorials/first-gitlab-to-nvftp-sync.md)
- [Run your first NVFTP-to-GitLab sync](docs/tutorials/first-nvftp-to-gitlab-sync.md)

### How-to guides

- [Configure GitLab CI/CD variables](docs/how-to/configure-cicd-variables.md)
- [Adopt the process in an NVIS OVA repository](docs/how-to/adopt-in-an-nvis-ova-repository.md)
- [Avoid redundant transfers](docs/how-to/avoid-redundant-transfers.md)
- [Run one or both synchronization directions](docs/how-to/run-sync-directions.md)
- [Schedule an inbound synchronization](docs/how-to/schedule-inbound-sync.md)
- [Migrate from `NVFTP_REMOTE_DIR`](docs/how-to/migrate-directory-variable.md)

### Reference

- [Configuration variables](docs/reference/configuration.md)
- [Pipeline jobs, outputs, and repository layout](docs/reference/pipeline.md)

### Explanation

- [Design, concurrency, and safety](docs/explanation/design-and-safety.md)

## Quick start

1. Follow [Configure GitLab CI/CD variables](docs/how-to/configure-cicd-variables.md) to add `NVFTP_USER`, the `NVFTP_PRIVATE_KEY` File variable, and the variables required by your direction.
2. Configure `NVFTP_UPLOAD_DIR`, `NVFTP_DOWNLOAD_DIR`, or both, depending on the intended direction.
3. For inbound synchronization, also configure the target-project variables listed in the [configuration reference](docs/reference/configuration.md).
4. Open **Build → Pipelines → New pipeline**, select `SYNC_DIRECTION`, and run the pipeline.

The inbound workflow never pushes to the target default branch and never merges its merge request. Human review remains required.

The application under [`examples/gitlab-to-nvftp-container`](examples/gitlab-to-nvftp-container/) is only a demonstration workload. Production repositories select their own Docker build context through CI/CD variables.
