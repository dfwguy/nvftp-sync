# Bootstrap runbook

## 1. Establish identities

1. Rotate the temporary personal GitLab token because it appeared in chat.
2. Have an `nvis-ova` Owner create a group access token with Developer role,
   expiration, and `api`, `read_api`, `read_repository`, and `write_repository`.
3. Store it only as `/etc/nvis-integration/credentials/gitlab_token`, mode `0600`,
   owned by `nvis-integrator`.
4. Copy the dedicated NVFTP private key into the credential directory and register
   its public key. Pin `transfer.nvftp.nvidia.com` in the service known-hosts file.
5. Create a Slack app from `slack-app-manifest.yaml`; store its `xoxb-` bot token and
   `xapp-` Socket Mode token as separate mode-0600 files.
6. Populate Slack user, approver, and channel IDs in configuration. Start with one
   private operations channel and at least two approvers.

Never place a credential in Slack, Git, a URL, a CI script, or shell history.

## 2. Harden GitLab projects

For the control plane and every managed destination:

1. use `main` as the default branch unless a documented exception exists;
2. protect it against direct pushes and force pushes;
3. require successful pipelines and resolved discussions;
4. require Code Owner/human approval for security, deployment, and CI files;
5. run incoming branches on runners that cannot access production credentials;
6. retain JUnit, scanner, SBOM, and provenance reports;
7. allow the hub identity to create branches and MRs, never merge them.

`nvis-ova/rack-status-pythoncm` currently uses protected
`feature/rack-status-pythoncm` as its default and does not require successful
pipelines or resolved discussions. Correct those settings in a separately approved
administrative change before automating publication.

## 3. Install the worker

1. Publish this control-plane repository to a private `nvis-ova` project.
2. Build a pinned wheel and verify its checksum.
3. Install it read-only under `/opt/nvis-integration`.
4. Create the `/data/nvis-integration` layout owned by `nvis-integrator` with mode
   `0750` directories and no access for validator containers to credentials.
5. Install `/etc/nvis-integration/config.toml` from the reviewed example.
6. Run `nvis-integration doctor --network` as the service account.
7. Run a synthetic end-to-end import into a disposable private project.
8. Enable and start the systemd service only after the dry run produces a valid MR.

## 4. Normalize the first Rack Status artifact

1. Preserve and record the four received source hashes.
2. Confirm the responsible owner attests `not_export_controlled` for GitLab-Master.
3. Set target `nvis-ova/rack-status-pythoncm` and source kind `snapshot`.
4. Preserve the incoming commit `cf68dfb2b1b2a7c4e3f6d7a529fb4675bad3be13`.
5. Generate the version-1 manifest and checksum envelope.
6. Re-run bundle, history-secret, tar-path, tar-secret, malware, and tree-equivalence
   gates.
7. Fetch the current protected destination tip immediately before integration.
8. Create `nvftp/<UTC-date>-cf68dfb2b1b2`, applying the incoming tree on top of that
   tip with provenance trailers.
9. Push the branch, open an MR, run all GitLab CI jobs, and attach validator reports.
10. If repository remediation is needed, hand a linked issue to the recoverable
    serial agent loop supplied by `nvis-ova-agentic-copier`; do not run an additional
    competing checkout loop in the hub.
11. A human reviews and merges in GitLab. The hub records the MR, merge commit, and
    final pipeline IDs in its audit ledger.

## 5. Slack workflow

The first command is intentionally structured:

```text
/nvis-import nvftp=/nvidia-space/shared/NscaleTX-16K/RackStatus_PythonCM \
  artifact=rack_status_pythoncm_20260914_cf68dfb2 target=auto
```

The bot responds with source, hashes, resolved destination, classification owner,
base/current commit comparison, changed-file summary, gates to run, and Approve or
Cancel buttons. Status and replay commands should be added only after the ingestion
path is proven; free-form chat can be layered on later as a parser that produces the
same structured request and requires confirmation.

## 6. Evidence and replay

Each cluster validation run receives a stable run ID and metadata manifest. Store raw
logs in content-addressed directories, compress after ingestion, and record hashes,
cluster alias, tool version, topology, timestamps, and redaction policy. A replay
creates a new job referencing the original hashes and an explicit new target; it
never mutates the original job or silently reuses current credentials/configuration.

## 7. Production acceptance

Do not call the hub production-ready until it passes restart/crash recovery, duplicate
Slack delivery, partial SFTP upload, stale default branch, token rotation, host-key
change, GitLab outage, Slack outage, disk-full, malicious archive, secret-in-history,
prompt-injection, failed CI, and backup/restore exercises.
