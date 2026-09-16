#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

repo_dir=${1:-tmp/target-repo}
reports_dir=${REPORTS_DIR:-$PWD/reports}
target_path=${TARGET_SYNC_PATH:-.}
branch_prefix=${SYNC_BRANCH_PREFIX:-nvftp-sync}

validate_target_configuration
validate_target_path "$target_path"
require_var TARGET_BASE_SHA

actual_base_sha=$(git -C "$repo_dir" rev-parse HEAD)
[ "$actual_base_sha" = "$TARGET_BASE_SHA" ] \
  || die "candidate base changed between validation and publication"

slug=${SOURCE_SLUG:-$(source_slug)}
safe_prefix=$(printf '%s' "$branch_prefix" | tr '[:upper:]' '[:lower:]' \
  | sed 's/[^a-z0-9._-]/-/g; s/-\{2,\}/-/g; s/^[.-]*//; s/[.-]*$//' | cut -c1-80)
[ -n "$safe_prefix" ] || die "SYNC_BRANCH_PREFIX has no safe branch characters"
branch=$safe_prefix/$slug
git check-ref-format --branch "$branch" >/dev/null 2>&1 || die "invalid sync branch name: $branch"

git -C "$repo_dir" diff --cached --quiet -- "$target_path" \
  && die "no candidate changes are staged for publication"
git -C "$repo_dir" config user.name "${GITLAB_SYNC_USER_NAME:-NVFTP Sync Bot}"
git -C "$repo_dir" config user.email "${GITLAB_SYNC_USER_EMAIL:-nvftp-sync@noreply.invalid}"
git -C "$repo_dir" checkout --quiet -B "$branch"
git -C "$repo_dir" commit --quiet -m "Sync NVFTP folder $(source_label) into target repository"

repo_url=$(target_repo_url)
remote_ref_file=$reports_dir/remote_branch.txt
if ! GIT_TERMINAL_PROMPT=0 GIT_ASKPASS="$SCRIPT_DIR/gitlab_git_askpass.sh" \
  git ls-remote "$repo_url" "refs/heads/$branch" >"$remote_ref_file"; then
  die "could not inspect the target sync branch"
fi
expected_oid=$(awk 'NR == 1 {print $1}' "$remote_ref_file")

GIT_TERMINAL_PROMPT=0 GIT_ASKPASS="$SCRIPT_DIR/gitlab_git_askpass.sh" \
  git -C "$repo_dir" push \
  "--force-with-lease=refs/heads/$branch:$expected_oid" \
  "$repo_url" "HEAD:refs/heads/$branch"

{
  cat "$reports_dir/sync.env"
  printf 'PUBLISHED_BRANCH=%s\n' "$branch"
} >"$reports_dir/publish.env"
printf 'Published validated candidate to %s in %s\n' "$branch" "$TARGET_PROJECT_PATH"
