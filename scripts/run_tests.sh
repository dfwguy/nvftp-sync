#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

repo_dir=${1:-tmp/target-repo}
require_var TARGET_TEST_COMMAND
[ -d "$repo_dir/.git" ] || die "target repository clone is missing: $repo_dir"

cd "$repo_dir"
printf '%s\n' 'Running the configured target repository test suite...'
exec sh -c "$TARGET_TEST_COMMAND"
