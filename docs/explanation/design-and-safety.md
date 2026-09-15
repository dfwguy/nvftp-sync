# Design, concurrency, and safety

## Why one branch contains two job graphs

The synchronization direction is a runtime choice, not a source-code variant. Keeping both job graphs on the same maintained branch prevents the pipeline definitions and shared SSH behavior from drifting apart. Local CI includes keep each graph readable while the root file owns the public selector.

## Why the example is isolated

The Flask container proves that the outbound workflow can build, export, and transfer an image, but it is not part of the synchronization framework. Keeping it under `examples/` prevents consumers from mistaking sample application files for required repository-root files. Configurable build variables allow each NVIS OVA repository to use the same process with its own Dockerfile and context.

## Why the directory variables are separate

An upload directory is a destination; a download directory is a source. A single `NVFTP_REMOTE_DIR` was ambiguous once both operations could run together. `NVFTP_UPLOAD_DIR` and `NVFTP_DOWNLOAD_DIR` express intent and prevent an accidental round trip.

## What `both` means

The two workflows are independent DAGs. The inbound pull can begin without waiting for the outbound upload, so it observes whatever was already present in its download directory when it connected. This makes `both` useful for operating two separate exchanges in one pipeline without implying data flow between them.

## Why inbound changes use a merge request

NVFTP content is external input. The pipeline stages it against an exact target-base commit, runs the target's test command, and publishes only after validation. It then proposes the result rather than modifying the protected branch. This preserves human review, target-project approvals, and the normal audit trail.

The branch is deterministic for each source, so subsequent runs update the same proposal. Publication uses `--force-with-lease`; an unexpected concurrent branch change fails instead of being silently overwritten.

## SSH trust model

Both directions require a dedicated passwordless key stored as a GitLab File variable. The scripts verify that the key is readable non-interactively and never print its contents.

When `NVFTP_KNOWN_HOSTS` is configured, strict host checking is enabled. Otherwise, `accept-new` protects subsequent connections after trusting the host on first use. Supplying an audited known-hosts entry is the stronger production configuration.

## Target-repository boundary

Inbound synchronization requires a separate target project and rejects the automation project's own path or ID. Candidate content therefore never becomes a commit in this automation repository, and the automation contains no operation that merges the target MR.
