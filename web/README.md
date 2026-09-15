# NVIS-OVA CI/CD Hub web console

Dependency-free responsive web console for the local NVIS-OVA control plane. The
production path is the authenticated loopback server, not a standalone static host:

```bash
nvis-integration --config /path/to/config.toml hub-serve \
  --web-root ./web \
  --auth-records /secure/portal-auth.json \
  --session-secret /secure/session-secret \
  --credential-root /secure/credentials
```

After login, the console requests JSON from `/api/v1/overview`, `/pipelines`, `/activity`,
`/repositories`, `/approvals`, `/audit`, and `/health`. If any endpoint is not
available after login, it switches to a conspicuous read-only demo mode. Demo
actions are simulated; credential values are never retained in browser storage.

The portal includes keyboard navigation, a skip link, reduced-motion support,
light/dark themes, responsive navigation, and a command center (`Ctrl/⌘ K`).
