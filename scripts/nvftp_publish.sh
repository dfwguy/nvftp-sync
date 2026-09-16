#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

require_var CI_PROJECT_DIR
require_var CI_COMMIT_SHA
require_var CI_DEFAULT_BRANCH

[ "${CI_COMMIT_BRANCH:-}" = "$CI_DEFAULT_BRANCH" ] \
  || die "outbound synchronization is allowed only from the target default branch"
[ "$(git -C "$CI_PROJECT_DIR" rev-parse HEAD)" = "$CI_COMMIT_SHA" ] \
  || die "target checkout does not match CI_COMMIT_SHA"

zero_sha=0000000000000000000000000000000000000000
if [ -n "${CI_COMMIT_BEFORE_SHA:-}" ] \
  && [ "$CI_COMMIT_BEFORE_SHA" != "$zero_sha" ] \
  && git -C "$CI_PROJECT_DIR" cat-file -e "$CI_COMMIT_BEFORE_SHA^{commit}" 2>/dev/null; then
  meaningful_changes=$(git -C "$CI_PROJECT_DIR" diff --name-only \
    "$CI_COMMIT_BEFORE_SHA" "$CI_COMMIT_SHA" \
    | grep -Ev '^(\.gitlab-ci\.yml|\.nvftp-sync-runtime/)' || true)
  if [ -z "$meaningful_changes" ]; then
    printf '%s\n' 'Only synchronization control files changed; NVFTP publication skipped.'
    exit 0
  fi
fi

require_var NVFTP_USER
require_var NVFTP_PRIVATE_KEY

target_path=${TARGET_SYNC_PATH:-.}
validate_target_path "$target_path"
source_dir=$CI_PROJECT_DIR/$target_path
mkdir -p "$source_dir"

NVFTP_HOST=${NVFTP_HOST:-transfer.nvftp.nvidia.com}
upload_dir=$(nvftp_upload_dir)
validate_nvftp_remote_dir "$upload_dir"
printf '%s' "$upload_dir" | LC_ALL=C grep -Eq '^[A-Za-z0-9._/ -]+$' \
  || die "NVFTP_UPLOAD_DIR contains characters unsafe for lftp"
printf '%s' "$NVFTP_USER" | LC_ALL=C grep -Eq '^[A-Za-z0-9._-]+$' \
  || die "NVFTP_USER contains unsafe characters"

key_file=$(mktemp)
lftp_commands=$(mktemp)
reports_dir=${REPORTS_DIR:-$CI_PROJECT_DIR/reports}
manifest_file=$reports_dir/nvftp-publish-manifest.txt
mkdir -p "$reports_dir"
trap 'rm -f "$key_file" "$lftp_commands"' EXIT HUP INT TERM
prepare_nvftp_ssh "$key_file"

tree_checksum=$(
  cd "$source_dir"
  find . -type f \
    ! -path './.git/*' \
    ! -path './.gitlab-ci.yml' \
    ! -path './.nvftp-sync-runtime/*' \
    -print | LC_ALL=C sort | while IFS= read -r file; do
    sha256sum "$file"
  done | sha256sum | awk '{print $1}'
)
{
  printf 'commit=%s\n' "$CI_COMMIT_SHA"
  printf 'tree_sha256=%s\n' "$tree_checksum"
  printf 'published_at=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
} >"$manifest_file"

strict_host_key_checking=${NVFTP_STRICT_HOST_KEY_CHECKING:-accept-new}
cat >"$lftp_commands" <<EOF
set cmd:fail-exit yes
set net:max-retries 2
set net:timeout 30
set sftp:connect-program "ssh -a -x -i $key_file -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=$strict_host_key_checking"
mirror --reverse --delete --verbose --exclude-glob .git/ --exclude-glob .gitlab-ci.yml --exclude-glob .nvftp-sync-runtime/ --exclude-glob .nvftp-sync-manifest "$source_dir" "$upload_dir"
put "$manifest_file" -o "$upload_dir/.nvftp-sync-manifest"
bye
EOF

lftp -f "$lftp_commands" "sftp://$NVFTP_USER@$NVFTP_HOST"
printf 'Published target commit %s path %s to NVFTP directory %s\n' \
  "$CI_COMMIT_SHA" "$target_path" "$upload_dir"
