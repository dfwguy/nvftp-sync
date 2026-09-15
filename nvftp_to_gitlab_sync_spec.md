
# NVFTP to GitLab Sync Implementation Spec

> Status: implemented. This document records the original inbound requirements. For current operating instructions and configuration, use the [Diátaxis documentation index](README.md#documentation).

Implement an inbound sync workflow for the GitLab repository [nvftp-sync](https://gitlab-master.nvidia.com/micheller/nvftp-sync) that detects changes from a designated NVFTP folder, validates them with the standard test suite, and creates a merge request into `main` for human review. Do not implement any automatic merge behavior.

## Goal

Build a GitLab CI-based workflow that:

1. Pulls a designated source folder from NVFTP over SFTP.
2. Compares the pulled contents against the source-of-truth contents tracked in the GitLab repo on `main`.
3. If there are changes, materializes the candidate version in a sync branch.
4. Runs the project’s standard test suite against the candidate version.
5. If tests pass, creates or updates a merge request targeting `main`.
6. If tests fail, does not create an MR and instead fails the pipeline with useful artifacts/logs for debugging.
7. Never automatically merges into `main`.

## High-level design

Treat NVFTP as the inbound delivery inbox and GitLab `main` as the reviewed system of record. The workflow must behave like a reconciliation and proposal engine, not a blind mirror.

The pipeline should be idempotent and safe to rerun. It should prefer updating a stable sync branch and MR for a given synced folder instead of opening duplicate MRs on every run.

## Expected workflow behavior

### No changes detected
- Exit successfully.
- Do not create a branch.
- Do not create an MR.

### Changes detected, tests fail
- Do not create or update an MR.
- Fail the pipeline.
- Publish artifacts including:
  - changed file list
  - diff summary
  - test logs
  - optional candidate snapshot

### Changes detected, tests pass
- Create or update a dedicated sync branch.
- Commit the candidate changes.
- Create or update an MR targeting `main`.
- Include a generated MR description summarizing the changes and test status.

## Repository assumptions

Assume the repo will contain:
- application code
- standard test suite
- GitLab CI config
- helper scripts for NVFTP pull, diffing, branch prep, and MR creation

The implementation should add or update a structure like:

```txt
.gitlab-ci.yml
scripts/
  nvftp_pull.sh
  prepare_candidate.sh
  detect_changes.sh
  run_tests.sh
  create_or_update_mr.sh
tmp/
  nvftp-source/        # runtime only, gitignored
synced-content/        # tracked repo path that mirrors the chosen NVFTP source folder
```

## Required CI/CD variables

Implement the workflow so it uses GitLab CI/CD variables rather than hardcoded secrets.

### NVFTP access
- `NVFTP_USER`
- `NVFTP_PRIVATE_KEY` (GitLab File variable; use passwordless RSA PEM key for CI compatibility)
- `NVFTP_DOWNLOAD_DIR` (`NVFTP_REMOTE_DIR` remains a deprecated compatibility fallback)

### GitLab MR automation
- `GITLAB_API_TOKEN` or equivalent token with permission to:
  - push branches
  - create/update merge requests

### Optional configuration
- `SYNC_BRANCH_PREFIX` default: `nvftp-sync`
- `TARGET_SYNC_PATH` default: `synced-content`
- `SYNC_SOURCE_NAME` human-readable source label for MR titles/descriptions

## Branching model

Use a deterministic sync branch per inbound source folder, for example:

```txt
nvftp-sync/<folder-name>
```

If GitLab branch naming constraints require sanitization, normalize folder names to a safe slug.

Do not push candidate changes directly to `main`.

## Merge request model

### MR title
Use a format like:

```txt
NVFTP sync: <folder-name> → main
```

### MR body
Include:
- source NVFTP folder
- sync timestamp
- target repo path
- changed file counts:
  - added
  - modified
  - deleted
- test suite result
- pipeline/job link
- optional generated summary of the change set

If an MR already exists for the sync branch, update it rather than opening duplicates.

## Pipeline stages

Implement these GitLab stages:

1. `pull_from_nvftp`
2. `diff_against_main`
3. `validate_candidate`
4. `publish_sync_branch`
5. `create_or_update_mr`

## Detailed stage behavior

### 1. `pull_from_nvftp`
Responsibilities:
- authenticate to NVFTP over SFTP using the existing CI secret pattern
- download the designated remote folder into a temporary workspace
- do not commit raw downloaded artifacts directly

Implementation notes:
- use the same GitLab File variable pattern that worked for outbound sync:
  - copy `$NVFTP_PRIVATE_KEY` into `~/.ssh/nvftp_key`
  - set mode `600`
- use `sftp` or a compatible batch mechanism to recursively pull the target folder into `tmp/nvftp-source/`
- fail fast if the remote source path is missing or inaccessible

### 2. `diff_against_main`
Responsibilities:
- check out current `main`
- copy the pulled NVFTP contents into the tracked repo target path such as `synced-content/`
- detect additions, modifications, and deletions versus `main`

Implementation notes:
- use a deterministic sync mechanism such as `rsync --delete`
- generate:
  - `changed_files.txt`
  - short diff summary
  - status output from `git status --porcelain`
- if no changes are detected, exit the pipeline successfully early

### 3. `validate_candidate`
Responsibilities:
- run the project’s standard test suite against the repo state that includes the NVFTP-delivered changes

Implementation notes:
- the tests must run against the candidate version, not current untouched `main`
- use the same command(s) the team treats as the standard gating suite
- examples may include `pytest`, `make test`, integration checks, linting, or build verification depending on repo norms
- publish logs and reports as artifacts

Decision rule:
- if tests fail, stop the workflow and do not create an MR

### 4. `publish_sync_branch`
Responsibilities:
- create or refresh the sync branch from latest `main`
- commit the validated candidate changes
- push the sync branch to GitLab

Implementation notes:
- only run if:
  - changes exist
  - tests passed
- use a standard commit message, for example:
  ```txt
  Sync NVFTP folder <folder-name> into repo
  ```

### 5. `create_or_update_mr`
Responsibilities:
- create a new MR targeting `main`, or update the existing MR for the sync branch
- populate the MR title and description with generated metadata

Implementation notes:
- use GitLab API
- if an open MR already exists from the sync branch to `main`, update its description instead of duplicating
- never merge automatically
- optionally add labels such as:
  - `nvftp-sync`
  - `automated-mr`
  - `needs-review`

## Agentic / Codex-friendly implementation guidance

Codex should implement the workflow in incremental, testable steps:

### Step 1
Add helper scripts for:
- pulling from NVFTP
- preparing candidate contents
- detecting git changes

### Step 2
Add or update `.gitlab-ci.yml` with pipeline stages through validation only.

### Step 3
Make the validation stage fail correctly on test failures and save artifacts.

### Step 4
Add branch publication logic.

### Step 5
Add GitLab API logic for MR creation/update.

### Step 6
Refine MR description generation with concise machine-generated summaries of changed files and validation status.

## Required safety constraints

Codex must preserve the following constraints:

- Never auto-merge into `main`.
- Never push candidate changes directly to `main`.
- Never create an MR if the validation stage fails.
- Never print secrets in logs.
- Use GitLab File variables for the SSH private key.
- Assume the CI key should be a passwordless RSA PEM key because that was the compatible working pattern in this environment.
- Keep secrets out of the repository.

## Suggested implementation details

### Candidate preparation
Use a clean checkout of `main`, then overlay the downloaded NVFTP contents into the tracked target path.

### Deletion handling
The sync logic must detect deletions in the inbound source and reflect them in the candidate branch. Use a sync mechanism that supports deletion awareness.

### Artifacts
On each pipeline run, save:
- changed file list
- diff summary
- test output
- optionally an archive of the candidate content

### Scheduling
The workflow should support:
- manual trigger
- scheduled polling

But the first implementation can be manual or scheduled without notification support.

## Out of scope for v1

Do not implement yet:
- Slack notification
- email notification
- automatic merge
- reviewer auto-assignment unless trivial
- production-grade retry orchestration beyond normal CI reruns

## Acceptance criteria

The implementation is complete when all of the following are true:

1. A GitLab pipeline can pull a designated NVFTP folder into the repo workspace.
2. The pipeline can detect whether the NVFTP-delivered content differs from `main`.
3. If there is no diff, the pipeline exits cleanly without creating an MR.
4. If there is a diff and tests fail, the pipeline fails and does not create an MR.
5. If there is a diff and tests pass, the pipeline creates or updates a sync branch and opens or updates an MR to `main`.
6. The MR includes a useful machine-generated summary and clearly states that human review/merge is required.
7. No step automatically merges into `main`.

## Final note for implementation

Prefer a simple, auditable implementation over a highly dynamic one. The most important properties are:
- reproducibility
- safe reviewability
- clear diff visibility
- test gating
- no automatic promotion into `main`


---

## Sources

- [https://gitlab-master.nvidia.com/micheller/nvftp-sync/-/jobs/432876693](https://gitlab-master.nvidia.com/micheller/nvftp-sync/-/jobs/432876693)
- [NVFTP - 2026 new process - WIP](https://nvidia.atlassian.net/wiki/spaces/STS/pages/3484319971)
