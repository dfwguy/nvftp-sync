# Security model

NVFTP packages and Slack input are untrusted. The importer accepts only strict
key/value commands, allowlisted users/channels and allowlisted NVFTP prefixes.
It verifies the complete artifact set, SHA-256 checksums, archive paths and
limits, secret patterns in both the current tar snapshot and every reachable
Git blob, ClamAV results, and Git bundle structure before creating any GitLab
content.

Downloaded code is never executed by the importer. Failures move artifacts to
quarantine. Credentials live outside the repository with mode `0600`. Logs and
Slack responses redact credentials. A Developer-scoped GitLab bot publishes;
protected branches, CI, and human approval provide the acceptance boundary.

Report suspected NVIDIA security issues through the NVIDIA PSIRT process, not
through a public issue.
