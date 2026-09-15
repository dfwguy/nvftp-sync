# NVIS-OVA CI/CD Hub

The hub is the staging control plane between NVFTP, Slack, and the canonical
`nvis-ova` GitLab namespace. It turns artifact delivery into one reviewable path:

```text
Slack request / portal upload
            |
            v
typed intent + RBAC + idempotency
            |
            v
human approval (no self-approval)
            |
            v
NVFTP download -> checksum -> archive safety -> secret scan -> malware scan
            |
            v
fresh default-branch clone -> snapshot/change-set integration -> feature branch + MR
            |
            v
GitLab CI + human review (the hub never approves or merges)
```

## Surfaces

- Slack Socket Mode: `/nvis`, direct messages, and app mentions.
- Portal: authenticated, responsive console bound to `127.0.0.1:8787`.
- CLI: diagnostics, audit verification, safe NVFTP listing, artifact packaging,
  planning, and individual job inspection.
- State: SQLite job/operation records plus two independent hash-chained audit logs.

## Slack language

Structured commands are the authoritative interface:

```text
/nvis import nvftp=/nvidia-space/shared/NscaleTX-16K/RackStatus_PythonCM artifact=RackStatus_PythonCM target=rack-status-pythoncm
/nvis branch project=rack-status-pythoncm name=feature/customer-validation base=main
/nvis fork project=rack-status-pythoncm name=feature/customer-validation base=main
/nvis status
/nvis status job=<32-character-job-id>
/nvis replay job=<32-character-job-id>
/nvis cancel job=<32-character-job-id>
```

Constrained natural language is also accepted in direct messages and mentions:

```text
stage RackStatus_PythonCM from /nvidia-space/shared/NscaleTX-16K/RackStatus_PythonCM into rack-status-pythoncm
create branch feature/customer-validation in rack-status-pythoncm from main
show status
```

Free-form text is never passed to a shell. Unknown fields, unsupported verbs,
unsafe paths, traversal, invalid refs, protected branch names, and out-of-group
projects fail closed. Import, replay, and branch creation all require an approver
different from the requester.

## Slack activation

Create or update the Slack app from `slack-app-manifest.yaml`, install it to the
intended workspace, and create an app-level token with `connections:write` for
Socket Mode. Place credentials directly on the VM; never paste them into chat:

```bash
install -m 600 /secure/source/xoxb-token \
  ~/cicd-hub/runtime/secrets/slack_bot_token
install -m 600 /secure/source/xapp-token \
  ~/cicd-hub/runtime/secrets/slack_app_token
```

Populate the three Slack allowlists in `~/cicd-hub/runtime/config.toml` with
immutable Slack IDs (not display names), then activate and verify:

```bash
systemctl --user restart nvis-ova-slack.service
systemctl --user status nvis-ova-slack.service
~/cicd-hub/runtime/venv/bin/nvis-integration \
  --config ~/cicd-hub/runtime/config.toml doctor --network
```

## Portal access

On the NVIDIA-internal `nvisova` VM, the user service is explicitly configured for
direct HTTP access at:

```text
http://nvisova.nvidia.com:8787
```

This internal-only exception uses an HttpOnly, SameSite=Strict session cookie but
does not provide transport encryption. Do not expose port 8787 outside NVIDIA's
trusted network. For encrypted transport without a reverse proxy, tunnel it:

```bash
ssh -L 8787:127.0.0.1:8787 hlakshminara@<staging-vm>
```

Open `http://127.0.0.1:8787`. The deployed roster uses NVIDIA email addresses as
login identities. Its initial password is readable only by the VM account at
`~/cicd-hub/runtime/secrets/initial-portal-password`. Replace the shared initial
password with unique credentials before relying on person-level audit attribution.

The portal exposes live counts and status for repositories, commits, forks, open
merge requests, recent pipelines, NVFTP, GitLab, Slack readiness, the audit store,
CPU/memory/disk/load, pending import approvals, and activity. Drag-and-drop stores
an artifact privately with a bounded size and appends an audit event; it does not
bypass the validation or approval pipeline.

## RBAC and secrets

Portal roles are `viewer`, `operator`, `approver`, and `admin`. Sessions are HMAC
signed, short-lived, HttpOnly, Secure, and SameSite=Strict. Mutations require CSRF
tokens. Credential GETs reveal only configured/not-configured state. Admin
rotation is write-only and atomically replaces a mode-0600 file; existing values
never return to the browser or logs.

The currently supported portal rotations are `gitlab_token`, `slack_bot_token`,
and `slack_app_token`. NVFTP SSH identity rotation is intentionally a separate key
ceremony because it requires registering a new public key and testing overlap
before revoking the old identity.

## Audit and recovery

```bash
~/cicd-hub/runtime/venv/bin/nvis-integration \
  --config ~/cicd-hub/runtime/config.toml audit-verify --json
~/cicd-hub/runtime/venv/bin/nvis-integration \
  --config ~/cicd-hub/runtime/config.toml portal-audit-verify
journalctl --user -u nvis-ova-hub.service -f
journalctl --user -u nvis-ova-slack.service -f
```

Job creation is idempotent using Slack event IDs. Failed downloaded artifacts move
to quarantine. Replay creates a new approval-gated job from the original immutable
request. The worker always reclones the current GitLab default branch immediately
before integration, avoiding long-lived customer forks and stale-base publication.

## Non-negotiable boundaries

- No force push, branch deletion, direct protected-branch write, approval, or merge.
- No GitLab publication before artifact classification attestation.
- No NVFTP path outside configured prefixes.
- No credentials in repository files, Slack text, audit details, or command output.
- No public-network portal bind; production or cross-network access requires TLS.
