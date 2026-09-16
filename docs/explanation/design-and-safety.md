# Design and safety

## Repository ownership

`nvftp-sync` owns reusable YAML and scripts only. The target repository owns the
content, pipeline schedule, proposal branches, MRs, and publication jobs. An
included pipeline runs in the target project's checkout and security context.

## Review boundary

Inbound NVFTP files are external proposals. They are overlaid with deletion
awareness, validated, and pushed to a deterministic non-protected branch. The
automation never merges the MR or pushes to the target default branch.

Outbound publication is selected only for default-branch pushes that change the
synchronized path. Thus an unreviewed sync branch cannot publish content.

## Workspace separation

Use a separate incoming directory and published directory. This prevents an
unapproved proposal from being interpreted as the approved state and removes a
feedback loop between inbound polling and outbound publication.

## Concurrency and completion

Both jobs share a target-project `resource_group`, serializing access. Outbound
mirroring includes deletions and writes its manifest last. Consumers that need
a completion signal should watch that manifest.

## Credentials

The NVFTP key and target access token live only in protected target-project
variables. Strict host verification is enabled when `NVFTP_KNOWN_HOSTS` is
provided. The tooling repository needs no synchronization secrets.
