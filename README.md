# NVIS integration worker

This host service is the control plane for a human-gated NVFTP/GitLab software
exchange. It accepts a strict `/nvis-import` Slack command over outbound-only
Socket Mode, resolves the NVFTP source through an operator-reviewed routing
catalog, verifies that the named artifact set exists, and presents an approval
button. Only an allowlisted approver can start ingestion. The worker then:

1. downloads the exact manifest, checksum, Git bundle, and tarball set;
2. validates checksums, provenance/classification, archive safety, passive secret
   patterns, malware, and the bundle;
3. resolves an exact project directly below `nvis-ova`;
4. creates a project or pushes a deterministic `nvftp/<date>-<sha>` branch;
5. opens an MR for an existing project and posts the review URL to Slack.

For flattened, unrelated snapshot bundles, it creates a new commit on top of the
destination's current protected default branch. It never joins unrelated Git
histories. It never approves or merges. Free-form Slack text is never passed to a
shell or agent.

Every job transition is recorded in a tamper-evident, hash-chained SQLite audit
ledger. See [the architecture](docs/architecture.md), [artifact contract](docs/artifact-contract.md),
and [bootstrap runbook](docs/bootstrap-runbook.md).

Michelle Ramirez's original GitLab-to-NVFTP container-transfer proof of concept is
preserved under `examples/gitlab-to-nvftp/`. It is reference material rather than
the production pipeline; the staging hub uses pinned SSH host keys and never prints
private-key material.

## Operations

```bash
sudo -u nvis-integrator /opt/nvis-integration/.venv/bin/nvis-integration doctor --network
sudo -u nvis-integrator /opt/nvis-integration/.venv/bin/nvis-integration \
  nvftp-list /nvidia-space/shared/NscaleTX-16K
systemctl status nvis-integration
journalctl -u nvis-integration
```

The service remains disabled until Slack and GitLab credentials plus user/channel
allowlists are installed. Never put tokens in this repository or a Slack message.
