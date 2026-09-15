# Adopt the process in an NVIS OVA repository

Use this foundation to give another NVIS OVA repository the same selectable transfer behavior without copying the example application.

## Add the process files

Bring the following framework paths into the repository:

```text
.gitlab-ci.yml
ci/
scripts/
```

Do not copy `examples/gitlab-to-nvftp-container` unless the repository needs the demonstration workload for testing.

## Point outbound synchronization at the repository workload

Set project CI/CD variables appropriate to the repository layout. For a root Dockerfile, use:

```text
OUTBOUND_BUILD_CONTEXT=.
OUTBOUND_DOCKERFILE=Dockerfile
OUTBOUND_ARCHIVE_NAME=<repository-name>.tar.gz
```

Leave `OUTBOUND_IMAGE_TAG` at its default unless images must be published under another registry tag.

Configure `NVFTP_USER`, `NVFTP_PRIVATE_KEY`, and `NVFTP_UPLOAD_DIR` by following [Configure GitLab CI/CD variables](configure-cicd-variables.md).

## Configure inbound synchronization when required

If the repository will orchestrate NVFTP-to-GitLab proposals, configure `NVFTP_DOWNLOAD_DIR` and the target-project variables. The target must be separate from the automation repository.

If only outbound synchronization is required, no inbound target variables are needed.

## Verify the adoption

1. Run `SYNC_DIRECTION=gitlab-to-nvftp` and confirm the repository's own image is uploaded.
2. If inbound is enabled, run `SYNC_DIRECTION=nvftp-to-gitlab` and confirm a no-change or reviewable-MR result.
3. Run `SYNC_DIRECTION=both` only after the upload and download directories are explicitly configured.
4. Keep the target default branch protected and verify that the automation token cannot bypass review.

When rolling out process updates across NVIS OVA repositories, update the framework paths consistently while leaving each repository's workload and CI/CD variable values local to that repository.
