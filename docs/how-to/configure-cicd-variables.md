# Configure GitLab CI/CD variables

Follow this guide when preparing an NVIS OVA repository to run either synchronization direction. It explains what to enter in GitLab and why the pipeline needs each value.

The concise lookup table is available separately in the [configuration reference](../reference/configuration.md).

## Decide which directions the repository will run

Choose the applicable column before creating variables:

| Variable group | GitLab → NVFTP | NVFTP → GitLab | Both |
| --- | --- | --- | --- |
| Shared NVFTP credentials | Required | Required | Required |
| Upload directory | Required | Not used | Required |
| Download directory | Not used | Required | Required |
| Outbound container settings | Required | Not used | Required |
| Target GitLab project settings | Not used | Required | Required |

You do not need to create irrelevant variables. For example, an outbound-only repository does not need a target-project token.

## Open the variables page

1. Open the GitLab project that will run this pipeline.
2. Select **Settings → CI/CD**.
3. Expand **Variables**.
4. Select **Add variable** for each value described below.
5. Leave **Environment scope** set to `All` unless the repository deliberately maintains environment-specific NVFTP workspaces.

Mark secret variables as **Protected** when pipelines run only on protected branches or tags. Confirm that the branch or schedule used for synchronization is also protected; otherwise GitLab will not expose those variables to the job.

## Configure the shared NVFTP identity

### `NVFTP_USER`

Create a variable with:

| Field | Value |
| --- | --- |
| Key | `NVFTP_USER` |
| Type | Variable |
| Value | The SSH username shown for the key in the NVFTP workspace |
| Protected | Recommended |

This is not an email address or GitLab username. NVFTP assigns it to the uploaded public key, and SFTP uses it when connecting to `transfer.nvftp.nvidia.com`.

### `NVFTP_PRIVATE_KEY`

Generate a dedicated, passwordless CI key on a trusted workstation:

```bash
ssh-keygen -t rsa -b 4096 -m PEM -C "nvftp-gitlab-ci" -f ~/.ssh/nvftp_ci_gitlab -N ""
```

Add the contents of `~/.ssh/nvftp_ci_gitlab.pub` to the NVFTP workspace. Then create the GitLab variable:

| Field | Value |
| --- | --- |
| Key | `NVFTP_PRIVATE_KEY` |
| Type | **File** |
| Value | The complete contents of `~/.ssh/nvftp_ci_gitlab` |
| Protected | Recommended |

Include the `BEGIN ... PRIVATE KEY` and `END ... PRIVATE KEY` lines. Do not paste the `.pub` file. The **File** type matters: GitLab writes the secret to a temporary file and gives the pipeline its path, which is what the transfer scripts expect.

Use a dedicated key because the pipeline must authenticate without prompting for a passphrase. Never reuse a personal workstation key.

### `NVFTP_KNOWN_HOSTS` (recommended)

Create this variable when an approved NVFTP host-key entry is available:

| Field | Value |
| --- | --- |
| Key | `NVFTP_KNOWN_HOSTS` |
| Type | File or Variable |
| Value | The trusted known-hosts entry for the NVFTP host |
| Protected | Recommended |

This pins the SFTP server identity. Without it, the scripts use `accept-new`, which trusts the first observed key and rejects later changes.

Do not obtain the value from an untrusted network connection. Use an entry supplied or verified by the service owner.

## Configure GitLab-to-NVFTP

### `NVFTP_UPLOAD_DIR`

Create a normal variable containing the existing remote directory that should receive the exported image, for example:

```text
/incoming/containers
```

The pipeline changes into this directory and uploads one `.tar.gz` file. The NVFTP identity must have write permission there.

### Point the build at the repository's container

The foundation repository defaults to its isolated example. In a normal NVIS OVA repository with a root Dockerfile, add:

| Key | Typical value | Why |
| --- | --- | --- |
| `OUTBOUND_BUILD_CONTEXT` | `.` | Sends the repository root as Docker build context |
| `OUTBOUND_DOCKERFILE` | `Dockerfile` | Selects the repository's production Dockerfile |
| `OUTBOUND_ARCHIVE_NAME` | `<repository-name>-$CI_COMMIT_SHORT_SHA.tar.gz` | Gives the exported image an identifiable filename |

Usually leave `OUTBOUND_IMAGE_TAG` unset so the pipeline uses `$CI_REGISTRY_IMAGE:$CI_COMMIT_SHORT_SHA`. Override it only when the repository has an established registry-tag convention.

Do not store these non-secret defaults as protected unless there is an organizational reason to restrict them.

## Configure NVFTP-to-GitLab

### `NVFTP_DOWNLOAD_DIR`

Create a normal variable containing the remote source folder, for example:

```text
/outgoing/release-bundle
```

The pipeline recursively downloads this folder and mirrors it into `TARGET_SYNC_PATH`. Files removed from NVFTP are proposed as deletions in the target merge request.

### Identify the target project

Open the separate GitLab project that will receive merge requests. Record:

- its namespace and project path, such as `nvis-ova/product-repo`;
- its numeric project ID from the project's overview page.

Create these variables in the automation project:

| Key | Example | Why |
| --- | --- | --- |
| `TARGET_PROJECT_PATH` | `nvis-ova/product-repo` | Builds the clone URL and identifies the repository in logs |
| `TARGET_PROJECT_ID` | `12345` | Addresses the target project through the GitLab API |

The target must not be the automation project. This boundary prevents downloaded content from modifying the framework repository itself.

### Create `GITLAB_API_TOKEN`

Create a project access token in the **target project**, or use a dedicated bot token governed by your team's credential policy.

For a project access token:

1. Open the target project, not the automation project.
2. Select **Settings → Access tokens**.
3. Create a token named for the automation, such as `nvftp-sync`.
4. Set an expiration date that follows the team's rotation policy.
5. Select the lowest role that can push non-protected branches and create merge requests; this is typically **Developer**.
6. Select the `api` and `write_repository` scopes.
7. Create the token and copy its value immediately. GitLab shows it only once.

Together, the role and scopes must provide enough access to:

- read the target repository;
- push the non-protected `nvftp-sync/...` branch;
- create and update merge requests through the API.

Do not grant permission to push to or bypass protection on the target default branch.

In the automation project, add:

| Field | Value |
| --- | --- |
| Key | `GITLAB_API_TOKEN` |
| Type | Variable |
| Value | The token value, shown once when created |
| Masked/hidden | Enable when GitLab accepts the token format |
| Protected | Recommended |

This variable is used for both authenticated Git operations and merge-request API calls. It is never written into the target repository's remote URL or retained as an artifact.

### Configure target validation

Create `TARGET_TEST_COMMAND` with the exact command maintainers trust for normal target changes. For example:

```text
python -m pip install -r requirements.txt && python -m pytest
```

The pipeline runs this command from the reconstructed target repository root. It publishes no branch or merge request if the command fails.

Optionally create:

| Key | Default | When to change it |
| --- | --- | --- |
| `TARGET_DEFAULT_BRANCH` | `main` | The target uses another default branch |
| `TARGET_SYNC_PATH` | `synced-content` | NVFTP content belongs in another repository-relative directory |
| `SYNC_SOURCE_NAME` | Download-folder name | A clearer branch and MR label is needed |
| `SYNC_BRANCH_PREFIX` | `nvftp-sync` | The target follows another automation-branch convention |

## Remove the legacy directory variable

If the project already has `NVFTP_REMOTE_DIR`, replace it with `NVFTP_UPLOAD_DIR` or `NVFTP_DOWNLOAD_DIR`. When using both directions, create both variables and then remove the legacy variable.

The compatibility fallback is intended only to keep existing one-direction pipelines working during migration.

## Verify the configuration

1. Start a manual pipeline on a protected ref.
2. Select only one `SYNC_DIRECTION` for the first test.
3. Confirm the relevant jobs appear and the other direction's jobs do not.
4. Confirm the job logs name the expected remote directory without printing any secret.
5. Test the second direction separately, if enabled.
6. Select `both` only after both individual tests pass.

If a job reports that a required variable is missing even though it exists in project settings, check whether the variable is protected while the selected ref is not.
