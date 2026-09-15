# Schedule an inbound synchronization

Use a GitLab pipeline schedule to poll an NVFTP folder and propose target-repository changes.

1. Open **Build → Pipeline schedules** in the automation project.
2. Create a schedule on a protected ref that can access protected CI/CD variables.
3. Choose the desired interval and time zone.
4. Add a schedule variable named `SYNC_DIRECTION` with value `nvftp-to-gitlab`.
5. Save and run the schedule once manually.
6. Confirm that a no-change run succeeds without publishing a branch or opening a merge request.

Do not rely on the repository default for an inbound schedule. The default is deliberately `gitlab-to-nvftp` so existing push behavior remains outbound.

Each changed run updates the deterministic sync branch and its existing open merge request. It does not create a new merge request on every polling interval.
