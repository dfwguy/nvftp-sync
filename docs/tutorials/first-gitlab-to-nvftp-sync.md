# Run the first approved publication

Outbound publication has no manual selector. Merge an MR that changes
`TARGET_SYNC_PATH` into the protected target default branch. Its push pipeline
will mirror the approved tree to `NVFTP_UPLOAD_DIR` and write
`.nvftp-sync-manifest` last.

Confirm the manifest's `commit` value matches the merged target commit. A
tooling-repository push and a target feature-branch push cannot run this job.
