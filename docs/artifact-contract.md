# Artifact envelope contract, version 1

Every import is a basename with four sibling files:

```text
<artifact>.MANIFEST.json
<artifact>.SHA256SUMS
<artifact>.git.bundle
<artifact>.tar.gz
```

The checksum file must name exactly the other three files using lowercase SHA-256.
Unexpected or missing members fail closed. SFTP transfer should upload temporary
names first and rename the checksum file last so the hub never observes a partially
published envelope as ready.

The manifest is UTF-8 JSON:

```json
{
  "schema_version": 1,
  "artifact": "rack_status_pythoncm_20260914_cf68dfb2",
  "target": "nvis-ova/rack-status-pythoncm",
  "source_kind": "snapshot",
  "classification": "not_export_controlled",
  "classification_attested_by": "responsible-owner@nvidia.com",
  "created_at": "2026-09-14T19:35:00Z",
  "base_commit": null
}
```

`classification_attested_by` is a responsible human, not the bot. GitLab-Master has
no export-control enforcement, so `unknown` and `export_controlled` are quarantined.

Use `source_kind=change-set` for a bundle created from a fresh clone of the target's
current default branch. Set its full 40-character `base_commit`. Use `snapshot` for
a sanitized tree with intentionally flattened history. Use `evidence` for replayable
validation evidence; evidence publication will use its own payload extension once
that phase is enabled.

The tar snapshot and Git bundle must represent the same source tree. The next
implementation gate will compare both tree inventories and hashes before accepting
an envelope; until then, this correspondence is reviewed manually.

The existing 16K Rack Status upload predates this contract. It remains quarantined
for publication until an owner supplies the manifest classification attestation and
the files are normalized into this envelope without altering their payload bytes.

Create an envelope from a clean, trusted checkout with:

```bash
nvis-integration package \
  --repo /absolute/path/to/checkout \
  --output /absolute/path/to/envelope \
  --artifact rack_status_pythoncm_YYYYMMDD_SHORTSHA \
  --target nvis-ova/rack-status-pythoncm \
  --source-kind snapshot \
  --classification-attested-by responsible-owner@nvidia.com
```

For `change-set`, also pass the full current destination commit as `--base-commit`.
The command refuses a dirty checkout or existing output files, builds both views from
the same commit, writes exact checksums, and verifies tree equivalence before success.
