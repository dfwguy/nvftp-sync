# Schedule inbound synchronization

Create the schedule in the target project, not in `nvftp-sync`:

1. Open **Build → Pipeline schedules** in the target project.
2. Select its protected default branch.
3. Choose the polling interval and time zone.
4. Ensure `NVFTP_SYNC_INBOUND_ENABLED=true` is defined by the target CI file or
   project variables.
5. Save and run the schedule once.

An unchanged run succeeds without creating a branch or MR. Changed runs update
the deterministic branch and existing open MR. No manual pipeline kickoff is
needed after the schedule is enabled.
