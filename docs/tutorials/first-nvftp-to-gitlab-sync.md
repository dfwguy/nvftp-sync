# Run the first inbound synchronization

1. Adopt the central template in the target repository.
2. Configure target-project variables and job-token access as described in the
   README.
3. Put a test file in `NVFTP_DOWNLOAD_DIR`.
4. Start a manual target default-branch pipeline with
   `SYNC_DIRECTION=nvftp-to-gitlab`.
5. Confirm the target validation passes and an MR is created.
6. Review and merge the MR.

After validation, enable the target-project schedule. Subsequent inbound runs
require no manual kickoff.
