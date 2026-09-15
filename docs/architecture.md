# NVIS staging-hub architecture

## Outcome

This VM is the durable orchestration point between customer/validation clusters,
NVFTP, Slack, and `gitlab-master`. It coordinates movement and review; it is not a
production cluster and it never silently merges code.

```text
cluster/operator
      |
      | signed/checksummed artifact envelope
      v
   NVFTP  <---------------- GitLab release/export pipeline
      |                                ^
      | SFTP, pinned host key          |
      v                                |
staging hub daemon <---- Socket Mode ---- Slack
      |
      +--> immutable inbox + hash-chained audit ledger
      +--> passive safety/classification/provenance gates
      +--> deterministic destination routing
      +--> isolated advisory validator agents
      +--> branch from latest protected destination tip
      +--> GitLab MR and CI --------------------------+
      +--> evidence index and replay plans
```

## Authority boundaries

| Component | May read | May write | Must never do |
|---|---|---|---|
| Slack bot | allowlisted command/channel metadata | job requests and status messages | accept free-form shell commands or secrets |
| NVFTP transport | allowlisted prefixes | optional export prefix only | disable host-key checking |
| ingestion worker | artifact envelope, destination metadata | local inbox/quarantine/work state | execute incoming code |
| validator agents | read-only disposable checkout and policy | bounded report files | receive GitLab/NVFTP/Slack credentials |
| GitLab publisher | target project and branch policy | feature branches and merge requests | push protected branches, approve, or merge |
| GitLab CI | proposed branch | test reports/release artifacts | expose secrets to untrusted job code |
| human approver | plan, diff, evidence, CI status | approve intake and merge in GitLab | attest classification without ownership |

The production GitLab identity is a group token with Developer role. Owner and
Maintainer identities are bootstrap-only. Default branches are protected and MRs
require successful pipelines and resolved discussions.

## Job state machine

```text
requested -> planned -> approved -> acquiring -> verified -> classified
    -> routed -> integrated -> validating -> review_ready -> merged -> exported
                    \-> quarantined / failed / cancelled
```

Each transition is transactional and appended to a SHA-256 hash chain. Restarted
workers resume only from explicitly restartable states. A terminal job can be
replayed as a new job referencing the original artifact hashes; its old records
are never edited.

## Routing

Routing is deterministic policy, not an unconstrained model decision. Exact NVFTP
source mappings are reviewed in configuration. A future advisory classifier can
rank GitLab candidates using repository metadata and tree similarity, but a new or
changed mapping requires human approval.

The first approved mapping is:

```text
/nvidia-space/shared/NscaleTX-16K/RackStatus_PythonCM
  -> nvis-ova/rack-status-pythoncm
```

## Integration modes

`change-set` artifacts retain a common Git ancestor. Their declared base must equal
the current destination tip; stale submissions are regenerated after pulling the
latest default branch.

`snapshot` artifacts may have flattened history. The hub compares Git trees, starts
from the current destination tip, replaces the index with the verified incoming
tree, and creates one provenance commit. It never uses `--allow-unrelated-histories`
and never force-pushes.

`evidence` artifacts contain validation results and logs. They are indexed by
cluster, engagement, run ID, tool version, time range, and SHA-256. Raw evidence is
retained outside Git; only redacted summaries and stable references belong in a
repository.

## Agent validation

Agents are advisory gates between integration and publication. Each runs in an
ephemeral Podman container or constrained process with:

- no credentials or host home directory;
- read-only source and a writable report directory;
- no cluster access and no GitLab write access;
- a fixed policy prompt owned by the control-plane repository;
- bounded runtime/output and a recorded model/prompt/policy version;
- prompt-injection findings treated as evidence, never instructions.

Initial validators cover destination correctness, secret/license policy, CI design,
tests, docs/release notes, unsafe shell, and artifact reproducibility. Their reports
are attached to the MR. Deterministic scanners and repository CI remain hard gates;
an agent verdict alone cannot approve publication.

Repository-level implementation and remediation should reuse the recoverable serial
GitLab agent loop from `nvis-ova/nvis-ova-agentic-copier`. The hub owns artifact
provenance, routing, and MR creation; the per-project loop owns bounded repository
work and validator receipts. The two systems exchange a linked GitLab issue/MR and
stable job ID instead of sharing credentials, prompts, or worktrees.

## Storage layout

```text
/opt/nvis-integration/                 immutable installed application
/etc/nvis-integration/config.toml      non-secret production configuration
/etc/nvis-integration/credentials/     mode-0600 service credentials
/etc/nvis-integration/known_hosts      pinned NVFTP/GitLab host keys
/data/nvis-integration/inbox/          immutable acquired envelopes
/data/nvis-integration/quarantine/     rejected envelopes and findings
/data/nvis-integration/work/           disposable integration worktrees
/data/nvis-integration/state/          SQLite ledger and checkpoints
/data/nvis-integration/evidence/       content-addressed validation evidence
/data/nvis-integration/reports/        redacted plans and validator reports
```

Back up `state`, `evidence`, `reports`, and the artifact hash catalog. Worktrees are
disposable. Secrets are rotated/recreated rather than backed up with application
data.

## Availability and observability

The systemd unit is outbound-only, unprivileged, restartable, and sandboxed. Metrics
include queue depth, state-transition counts, job duration, bytes transferred,
quarantine reasons, GitLab API latency, Slack connection health, and last successful
backup. Logs are structured JSON with job IDs and artifact hashes but no token,
credential, customer payload, or unredacted agent prompt content.

Alerts go to a separate operations channel. Slack is a control surface, not the
system of record; SQLite plus artifact hashes and GitLab MRs are authoritative.
