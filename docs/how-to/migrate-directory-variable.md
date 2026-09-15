# Migrate from `NVFTP_REMOTE_DIR`

Earlier versions used `NVFTP_REMOTE_DIR` for both uploads and downloads. Replace it before using `SYNC_DIRECTION=both`.

## One-direction projects

For an outbound project, rename:

```text
NVFTP_REMOTE_DIR → NVFTP_UPLOAD_DIR
```

For an inbound project, rename:

```text
NVFTP_REMOTE_DIR → NVFTP_DOWNLOAD_DIR
```

## Projects using both directions

Create both variables explicitly:

```text
NVFTP_UPLOAD_DIR=/incoming/containers
NVFTP_DOWNLOAD_DIR=/outgoing/release-bundle
```

Then remove `NVFTP_REMOTE_DIR`.

## Compatibility behavior

`NVFTP_REMOTE_DIR` remains a fallback when the direction-specific variable is absent. The job prints a deprecation warning when it uses that fallback. In `both` mode, a lone legacy variable would make both workflows use the same directory, so explicit direction-specific variables are strongly recommended.
