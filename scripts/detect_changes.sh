#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

repo_dir=${1:-tmp/target-repo}
reports_dir=${REPORTS_DIR:-$PWD/reports}
target_path=${TARGET_SYNC_PATH:-synced-content}

validate_target_configuration
validate_target_path "$target_path"
[ -d "$repo_dir/.git" ] || die "target repository clone is missing: $repo_dir"
mkdir -p "$reports_dir"

base_sha=$(git -C "$repo_dir" rev-parse HEAD)
git -C "$repo_dir" add -A -- "$target_path"
git -C "$repo_dir" diff --cached --no-renames --name-status -- "$target_path" >"$reports_dir/changed_files.txt"
git -C "$repo_dir" diff --cached --no-renames --stat -- "$target_path" >"$reports_dir/diff_summary.txt"
git -C "$repo_dir" status --porcelain -- "$target_path" >"$reports_dir/git_status.txt"

if [ -s "$reports_dir/changed_files.txt" ]; then
  has_changes=true
else
  has_changes=false
fi

added=$(awk '$1 ~ /^A/ {count++} END {print count+0}' "$reports_dir/changed_files.txt")
modified=$(awk '$1 ~ /^(M|T)/ {count++} END {print count+0}' "$reports_dir/changed_files.txt")
deleted=$(awk '$1 ~ /^D/ {count++} END {print count+0}' "$reports_dir/changed_files.txt")
slug=$(source_slug)
[ -n "$slug" ] || die "could not derive a safe source slug"

{
  printf 'HAS_CHANGES=%s\n' "$has_changes"
  printf 'FILES_ADDED=%s\n' "$added"
  printf 'FILES_MODIFIED=%s\n' "$modified"
  printf 'FILES_DELETED=%s\n' "$deleted"
  printf 'SOURCE_SLUG=%s\n' "$slug"
  printf 'TARGET_BASE_SHA=%s\n' "$base_sha"
} >"$reports_dir/sync.env"

printf 'Changes: %s (added=%s modified=%s deleted=%s)\n' "$has_changes" "$added" "$modified" "$deleted"
cat "$reports_dir/diff_summary.txt"
