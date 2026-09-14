# NVFTP to GitLab inbound sync automation

This repository orchestrates inbound synchronization from an NVFTP folder into a separate GitLab target repository. The target repository remains the reviewed source of truth: this automation can propose changes on a sync branch and create or update a merge request, but it never pushes to `main` and never merges an MR.

The automation and target repositories must be different projects. The scripts reject a target project path or ID that matches this automation project.

## Pipeline behavior

| NVFTP comparison | Validation | Result |
| --- | --- | --- |
| No changes | Skipped | Pipeline succeeds; no target branch or MR is created |
| Changes | Fails | Pipeline fails; reports, changed-file metadata, and the test log are retained |
| Changes | Passes | A deterministic target branch is updated and an MR into `main` is created or updated |

Human review and merge are always required.

## Pipeline stages

1. `pull_from_nvftp` downloads the configured remote folder over SFTP into a temporary artifact.
2. `diff_against_target_main` clones the separate target repository, overlays the download at `TARGET_SYNC_PATH` with deletion awareness, and records the diff against the target's `main` commit.
3. `validate_candidate` reconstructs that exact candidate commit and runs `TARGET_TEST_COMMAND` from the target repository root.
4. `publish_sync_branch` runs only after validation succeeds and pushes `nvftp-sync/<folder-name>` to the target repository.
5. `create_or_update_mr` creates an MR in the target project, or updates the existing open MR for the same source branch.

The target base commit is carried between jobs as `TARGET_BASE_SHA`. This ensures the tested tree and published tree use the same target `main` snapshot.

## Required GitLab CI/CD variables

Configure these in the automation project under **Settings → CI/CD → Variables**.

| Variable | Type | Purpose |
| --- | --- | --- |
| `NVFTP_USER` | Variable | NVFTP-generated SSH username |
| `NVFTP_PRIVATE_KEY` | **File** | Dedicated passwordless RSA PEM private key |
| `NVFTP_REMOTE_DIR` | Variable | Remote NVFTP folder to download |
| `GITLAB_API_TOKEN` | Masked, protected Variable | Token whose user can clone, push branches, and manage MRs in the target project |
| `TARGET_PROJECT_PATH` | Variable | Target namespace/project, for example `team/product-repo` |
| `TARGET_PROJECT_ID` | Variable | Numeric GitLab project ID for the target repository |
| `TARGET_TEST_COMMAND` | Variable | The target repository's standard gating command |

The token needs API access plus repository read/write permission in the target project. The token owner must have a target-project role that permits branch pushes and MR creation. Do not configure it with permission to bypass target protected-branch rules.

A typical Python target test command is:

~~~text
python -m pip install -r requirements.txt && python -m pytest
~~~

The command runs from the reconstructed target repository root. The validation job currently uses `python:3.12-slim` and installs `git`, `make`, and `rsync`. If the target suite needs a different runtime, change only the `validate-candidate` image/setup in `.gitlab-ci.yml`; the gating behavior remains the same.

### Optional variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `TARGET_DEFAULT_BRANCH` | `main` | Target branch used as the comparison base and MR target |
| `TARGET_SYNC_PATH` | `synced-content` | Repo-relative path replaced by the NVFTP folder contents |
| `TARGET_REPO_URL` | Derived from `CI_SERVER_URL` and `TARGET_PROJECT_PATH` | HTTPS clone/push URL for a target on another GitLab host or at a custom URL |
| `TARGET_GITLAB_API_URL` | `CI_API_V4_URL` | GitLab v4 API base URL for the target project |
| `SYNC_BRANCH_PREFIX` | `nvftp-sync` | Prefix for deterministic target branches |
| `SYNC_SOURCE_NAME` | NVFTP folder basename | Human-readable source label used in branch/MR metadata |
| `NVFTP_HOST` | `transfer.nvftp.nvidia.com` | NVFTP SFTP host |
| `NVFTP_KNOWN_HOSTS` | unset | Known-hosts content or File variable; when set, strict host verification is enabled |
| `GITLAB_SYNC_USER_NAME` | `NVFTP Sync Bot` | Commit author name |
| `GITLAB_SYNC_USER_EMAIL` | `nvftp-sync@noreply.invalid` | Commit author email |

`TARGET_SYNC_PATH` must be a safe repository-relative subdirectory. Root paths, `.git`, and parent traversal are rejected. The sync uses checksum comparison and `rsync --delete`, so content changes are detected even when size/timestamps match, and files absent from NVFTP are proposed as deletions.

## NVFTP key setup

Use a dedicated passwordless RSA key in PEM format because that is the proven non-interactive format for this runner/OpenSSH environment:

~~~bash
ssh-keygen -t rsa -b 4096 -m PEM -C "nvftp-gitlab-ci" -f ~/.ssh/nvftp_ci_gitlab -N ""
~~~

Upload the public key to the NVFTP workspace:

~~~bash
cat ~/.ssh/nvftp_ci_gitlab.pub
~~~

Store the full private key file contents in `NVFTP_PRIVATE_KEY` as a GitLab **File** variable. The pull helper verifies that the variable resolves to a file and that the key can be read without a passphrase. Key contents are never printed.

For stronger host verification, store the trusted NVFTP known-hosts entry in `NVFTP_KNOWN_HOSTS` as either a normal variable or a File variable.

## Target repository setup

1. Create a project access token or bot/user token that can read and write the target repository and call the merge-request API.
2. Give that identity the minimum target-project role needed to push non-protected branches and create MRs.
3. Keep `main` protected and require normal human review/approval.
4. Set `TARGET_PROJECT_PATH` and `TARGET_PROJECT_ID` to the target project, not this automation project.
5. Set `TARGET_TEST_COMMAND` to the same gating suite maintainers trust for normal target changes.
6. Ensure `TARGET_SYNC_PATH` is the directory intended to mirror the NVFTP source folder.

The branch name is deterministic per source label, for example `nvftp-sync/release-bundle`. Reruns update that branch and the matching open MR instead of creating duplicates. Publication uses `--force-with-lease` so a concurrent or unexpected branch update causes the job to fail instead of being silently overwritten.

## Running the workflow

The CI workflow accepts manual, scheduled, API, and trigger pipelines. Ordinary push pipelines do not start an NVFTP sync, which avoids accidental runs without protected credentials.

For a manual run:

1. Open **Build → Pipelines → New pipeline** in the automation project.
2. Select a protected ref that can access the protected CI/CD variables.
3. Run the pipeline.
4. Review artifacts from `diff-against-target-main` and `validate-candidate`.
5. If validation passed and a diff exists, follow the target MR URL printed by the last job.

For scheduled polling, create a pipeline schedule on the same protected ref. Each run reconciles the full NVFTP folder against the configured target path.

## Artifacts and audit trail

The pipeline retains artifacts for seven days:

- `changed_files.txt`: added, modified, and deleted target paths
- `diff_summary.txt`: Git diff statistics
- `git_status.txt`: porcelain status for the candidate
- `sync.env`: non-secret decision metadata and the pinned target base SHA
- `test.log`: complete target validation output
- `mr_description.md` and API response metadata when an MR is published
- the pulled NVFTP snapshot through validation, to help diagnose failures

No private key or GitLab token is stored in artifacts. Git authentication uses an askpass helper, so the target token is not embedded in a repository remote URL.

## Safety properties

- The automation project and target/source-of-truth project are explicitly separate.
- Candidate content is never committed to the automation repository.
- No-diff runs never push a branch or call the MR API.
- Failed validation stops the pipeline before branch publication.
- Candidate branches are based on the exact target `main` SHA used during validation.
- No command pushes to `main`.
- The MR helper only lists, creates, or updates MRs; it has no merge operation.
- Human review and merge remain mandatory.
