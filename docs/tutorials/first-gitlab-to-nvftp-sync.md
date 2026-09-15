# Run your first GitLab-to-NVFTP sync

This tutorial walks through building the explicitly isolated example container and uploading its compressed image archive to NVFTP.

## Before you begin

You need access to this GitLab project, an NVFTP workspace, and an NVFTP-generated SSH username.

Create a dedicated passwordless RSA key in PEM format:

```bash
ssh-keygen -t rsa -b 4096 -m PEM -C "nvftp-gitlab-ci" -f ~/.ssh/nvftp_ci_gitlab -N ""
```

Add the contents of `~/.ssh/nvftp_ci_gitlab.pub` to the NVFTP workspace's SSH keys.

## Configure GitLab

In **Settings → CI/CD → Variables**, add:

| Variable | Type | Example |
| --- | --- | --- |
| `NVFTP_USER` | Variable | NVFTP-generated SSH username |
| `NVFTP_PRIVATE_KEY` | File | Contents of `~/.ssh/nvftp_ci_gitlab` |
| `NVFTP_UPLOAD_DIR` | Variable | `/incoming/containers` |

The private key must be a GitLab **File** variable. The workflow expects its value to be a path to the temporary key file created by GitLab.

## Run the pipeline

1. Open **Build → Pipelines → New pipeline**.
2. Select the branch to test.
3. Leave `SYNC_DIRECTION` set to `gitlab-to-nvftp`.
4. Select **Run pipeline**.

The pipeline builds the workload in `examples/gitlab-to-nvftp-container`, pushes the image, exports it as `container-image.tar.gz`, and uploads that file plus `container-image.tar.gz.sha256` to `NVFTP_UPLOAD_DIR`. A rerun skips the archive upload when the remote checksum already matches.

## Confirm the result

Check these three places:

1. In GitLab, open **Deploy → Container Registry** and find the image tagged with the pipeline commit SHA.
2. Open the `export-image` job and confirm its artifacts contain the `.tar.gz` archive.
3. Open the configured NVFTP directory and confirm the same archive is present.

You have now completed an outbound synchronization. The [direction how-to guide](../how-to/run-sync-directions.md) shows how to select the other modes.
