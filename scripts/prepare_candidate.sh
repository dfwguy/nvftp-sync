#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

repo_dir=${1:-tmp/target-repo}
source_dir=${2:-tmp/nvftp-source}
target_path=${TARGET_SYNC_PATH:-synced-content}

validate_target_path "$target_path"
[ -d "$repo_dir/.git" ] || die "target repository clone is missing: $repo_dir"
[ -d "$source_dir" ] || die "downloaded NVFTP source is missing: $source_dir"

mkdir -p "$repo_dir/$target_path"
rsync -a --checksum --delete --exclude='.git/' "$source_dir/" "$repo_dir/$target_path/"
printf 'Prepared candidate in %s at %s\n' "$TARGET_PROJECT_PATH" "$target_path"
