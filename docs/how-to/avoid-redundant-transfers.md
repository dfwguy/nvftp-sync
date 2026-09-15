# Avoid redundant NVFTP transfers

Use the outbound checksum sidecar and, when the producer can honor the required contract, an inbound content manifest to reduce repeated data transfer.

## Skip unchanged GitLab-to-NVFTP uploads

No additional variable is required. The outbound pipeline:

1. exports the image under a stable local tag;
2. creates a deterministic gzip archive;
3. calculates its SHA-256;
4. downloads only `<archive-name>.sha256` from NVFTP;
5. skips the archive upload when the remote and local checksums match;
6. otherwise uploads the archive followed by its new checksum sidecar.

Keep `OUTBOUND_ARCHIVE_NAME` stable, for example:

```text
OUTBOUND_ARCHIVE_NAME=my-ova.tar.gz
```

Using `my-ova-$CI_COMMIT_SHORT_SHA.tar.gz` creates a distinct remote filename on every commit. Since no checksum exists at the new path, the pipeline must upload it even when the image content is unchanged.

Changing to a stable name does not delete older commit-named archives. After verifying the stable archive and checksum, handle those older files through the workspace's approved retention or cleanup process; this pipeline does not delete remote outbound artifacts.

To deliberately replace the remote files regardless of the checksum, start the pipeline with:

```text
OUTBOUND_FORCE_UPLOAD=true
```

The checksum check avoids the NVFTP archive upload. It does not skip the GitLab build, registry push, image export, or transfer of job artifacts between GitLab runners.

## Skip unchanged NVFTP-to-GitLab downloads

SFTP does not expose a recursive checksum for an arbitrary directory. Enable this optimization only when the system publishing to NVFTP can create a manifest that changes whenever any synchronized file changes.

The manifest can contain individual SHA-256 entries, a release identifier, or another deterministic representation of the complete delivery. The synchronization pipeline hashes the manifest file itself; it does not interpret its format.

### Publish the delivery safely

The producing process must:

1. upload all new or changed content;
2. remove content that no longer belongs in the delivery;
3. generate a manifest representing the final complete folder;
4. upload or rename the manifest into place **last**.

Updating the manifest last is the commit signal. If content changes without a corresponding manifest change, the consumer can incorrectly skip the folder.

### Configure the consumer

Add a GitLab CI/CD variable containing the full remote manifest path:

```text
NVFTP_DOWNLOAD_MANIFEST=/outgoing/manifests/my-ova.sha256
```

Prefer a path outside `NVFTP_DOWNLOAD_DIR`. A manifest stored inside the downloaded folder becomes part of the mirrored target content unless the target workflow deliberately removes it.

On each inbound pipeline, the pull job downloads this small file first. It skips the recursive folder download only when the manifest matches the checkpoint from the last fully successful inbound pipeline.

The checkpoint is not advanced when validation, branch publication, or MR processing fails. The next pipeline therefore downloads and retries the same delivery. If the GitLab cache is missing or evicted, the pipeline safely performs a full download.

### Disable manifest optimization

Remove `NVFTP_DOWNLOAD_MANIFEST`. The pipeline returns to downloading the folder on every inbound run and uses its existing Git comparison to avoid unnecessary branches and merge requests.

Do not point `NVFTP_DOWNLOAD_MANIFEST` at a timestamp or file that can remain unchanged while delivery content changes.
