# Run your first NVFTP-to-GitLab sync

This tutorial imports an NVFTP folder into a path in a separate GitLab repository. The pipeline validates the candidate and proposes it through a merge request.

## Before you begin

Complete the SSH-key setup in the [outbound tutorial](first-gitlab-to-nvftp-sync.md). You also need:

- a separate GitLab target project;
- a token whose user can clone that project, push non-protected branches, and manage merge requests;
- a test command appropriate for the target project.

The automation project cannot also be the target project.

## Configure GitLab

In **Settings → CI/CD → Variables**, add the shared `NVFTP_USER` and `NVFTP_PRIVATE_KEY` values, then add:

| Variable | Example |
| --- | --- |
| `NVFTP_DOWNLOAD_DIR` | `/outgoing/release-bundle` |
| `TARGET_PROJECT_PATH` | `team/product-repo` |
| `TARGET_PROJECT_ID` | `12345` |
| `TARGET_TEST_COMMAND` | `python -m pip install -r requirements.txt && python -m pytest` |
| `GITLAB_API_TOKEN` | A masked, protected token |

The default destination inside the target repository is `synced-content`. Set `TARGET_SYNC_PATH` if another repository-relative directory is required.

Keep the target default branch protected. The token should be allowed to push working branches, not bypass the protected branch.

## Run the pipeline

1. Open **Build → Pipelines → New pipeline**.
2. Select a protected branch that can access the protected token.
3. Change `SYNC_DIRECTION` to `nvftp-to-gitlab`.
4. Select **Run pipeline**.

The jobs download the folder, compare it with the target repository, run the configured test command, publish a deterministic `nvftp-sync/<source>` branch, and open or update a merge request.

## Confirm the result

If files changed and validation passed, the final job prints the merge-request URL. Open it and confirm:

- the source branch begins with `nvftp-sync/`;
- the target is the configured default branch;
- additions, modifications, and deletions match the NVFTP folder;
- the pipeline description reports the expected target base commit.

Review and merge the proposal using the target project's normal process. A no-change run succeeds without creating a branch or merge request.
