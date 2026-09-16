# Configure target-project CI/CD variables

Configure synchronization secrets in the target project under
**Settings → CI/CD → Variables**.

Required protected variables:

- `NVFTP_USER`: NVFTP SSH identity.
- `NVFTP_PRIVATE_KEY`: passwordless private key, using GitLab's **File** type.
- `NVFTP_DOWNLOAD_DIR`: incoming proposal directory.
- `NVFTP_UPLOAD_DIR`: approved publication directory.
- `GITLAB_API_TOKEN`: masked target-project token able to push proposal
  branches and use the MR API.

Recommended:

- `NVFTP_KNOWN_HOSTS`: audited NVFTP host entry, as a File or normal variable.

Non-secret settings such as `TARGET_SYNC_PATH`, `TARGET_TEST_COMMAND`, and the
two enable flags normally live in the target `.gitlab-ci.yml`.

Protected variables are available only when the target schedule runs on a
protected ref. The access token must not be able to bypass protection on the
default branch.
