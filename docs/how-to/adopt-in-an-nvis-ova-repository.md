# Adopt synchronization in a target repository

1. Include `/ci/target-sync.yml` from a pinned `nvftp-sync` release in the
   target `.gitlab-ci.yml`.
2. Set `NVFTP_SYNC_TOOLS_REF` to the same release.
3. Set both enable flags to `true`, set `TARGET_SYNC_PATH=.` for codebase-root
   synchronization, and provide `TARGET_TEST_COMMAND`.
4. Add the target project to the `nvftp-sync` CI job-token allowlist.
5. Configure the protected NVFTP and GitLab token variables in the target.
6. Keep the target default branch protected; the automation token should push
   proposal branches but never bypass review.
7. Create a target-project schedule on its protected default branch.
8. Run one manual inbound pipeline with
   `SYNC_DIRECTION=nvftp-to-gitlab`, review its MR, and merge it.
9. Verify that the resulting default-branch pipeline publishes the approved
   codebase to `NVFTP_UPLOAD_DIR`.

The target contains only the small include and project-specific non-secret
settings. Reusable YAML and scripts remain in `nvftp-sync`.
