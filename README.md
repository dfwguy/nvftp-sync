# Bidirectional GitLab and NVFTP synchronization

This repository hosts two selectable GitLab pipelines on one branch:

- `gitlab-to-nvftp` builds the sample container, exports it, and uploads the archive to NVFTP.
- `nvftp-to-gitlab` downloads an NVFTP folder, validates it against a separate target repository, and opens or updates a merge request.
- `both` runs both independent workflows in the same pipeline.

The default is `gitlab-to-nvftp`, which preserves the behavior of ordinary push pipelines. Choose a different value for `SYNC_DIRECTION` when starting a manual, scheduled, API, or trigger pipeline.

## Documentation

The documentation follows the [Diátaxis](https://diataxis.fr/) organization:

### Tutorials

- [Run your first GitLab-to-NVFTP sync](docs/tutorials/first-gitlab-to-nvftp-sync.md)
- [Run your first NVFTP-to-GitLab sync](docs/tutorials/first-nvftp-to-gitlab-sync.md)

### How-to guides

- [Run one or both synchronization directions](docs/how-to/run-sync-directions.md)
- [Schedule an inbound synchronization](docs/how-to/schedule-inbound-sync.md)
- [Migrate from `NVFTP_REMOTE_DIR`](docs/how-to/migrate-directory-variable.md)

### Reference

- [Configuration variables](docs/reference/configuration.md)
- [Pipeline jobs, outputs, and repository layout](docs/reference/pipeline.md)

### Explanation

- [Design, concurrency, and safety](docs/explanation/design-and-safety.md)

## Quick start

1. Configure `NVFTP_USER` and the `NVFTP_PRIVATE_KEY` File variable in **Settings → CI/CD → Variables**.
2. Configure `NVFTP_UPLOAD_DIR`, `NVFTP_DOWNLOAD_DIR`, or both, depending on the intended direction.
3. For inbound synchronization, also configure the target-project variables listed in the [configuration reference](docs/reference/configuration.md).
4. Open **Build → Pipelines → New pipeline**, select `SYNC_DIRECTION`, and run the pipeline.

The inbound workflow never pushes to the target default branch and never merges its merge request. Human review remains required.
