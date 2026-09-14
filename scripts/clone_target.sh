#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

repo_dir=${1:-tmp/target-repo}
base_sha=${2:-}
default_branch=${TARGET_DEFAULT_BRANCH:-main}

validate_target_configuration
case "$repo_dir" in
  tmp/*) case "$repo_dir" in */../*|*/..|*/./*|*/.) die "unsafe target clone directory: $repo_dir" ;; esac ;;
  *) die "target clone directory must be below tmp/" ;;
esac

repo_url=$(target_repo_url)
rm -rf "$repo_dir"
mkdir -p "$(dirname "$repo_dir")"
GIT_TERMINAL_PROMPT=0 GIT_ASKPASS="$SCRIPT_DIR/gitlab_git_askpass.sh" \
  git clone --quiet --branch "$default_branch" --single-branch "$repo_url" "$repo_dir"

if [ -n "$base_sha" ]; then
  git -C "$repo_dir" cat-file -e "$base_sha^{commit}" 2>/dev/null \
    || die "validated target base commit is no longer available: $base_sha"
  git -C "$repo_dir" checkout --quiet --detach "$base_sha"
fi

printf 'Cloned target %s at %s\n' "$TARGET_PROJECT_PATH" "$(git -C "$repo_dir" rev-parse HEAD)"
