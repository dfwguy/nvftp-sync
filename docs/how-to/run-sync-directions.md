# Run one or both synchronization directions

Use the `SYNC_DIRECTION` pipeline variable to select which job graph is created.

## Run GitLab to NVFTP

Set:

```text
SYNC_DIRECTION=gitlab-to-nvftp
```

Configure `NVFTP_UPLOAD_DIR`. This is the default selection and is appropriate for ordinary push pipelines.

## Run NVFTP to GitLab

Set:

```text
SYNC_DIRECTION=nvftp-to-gitlab
```

Configure `NVFTP_DOWNLOAD_DIR` and all required target-project variables.

## Run both

Set:

```text
SYNC_DIRECTION=both
```

Configure both directory variables. They may point to different NVFTP directories and normally should do so.

The two workflows are independent. `pull-from-nvftp` has no dependency on the outbound jobs and can start as soon as a runner is available. Therefore, `both` does not mean “upload and then download the uploaded archive.” It means “run an outbound sync and an inbound sync in the same pipeline.”

To implement an intentional round trip, use two separate pipelines and start the inbound pipeline only after the outbound pipeline succeeds.

## Start a manual pipeline

1. Open **Build → Pipelines → New pipeline**.
2. Choose the ref.
3. Select one of the offered `SYNC_DIRECTION` values.
4. Run the pipeline.

For API or trigger pipelines, pass the same variable in the request. For schedules, follow [Schedule an inbound synchronization](schedule-inbound-sync.md).
