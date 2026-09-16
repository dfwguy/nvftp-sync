#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

require_var CI_PROJECT_DIR
require_var CI_PROJECT_PATH
require_var CI_PROJECT_ID
require_var CI_COMMIT_SHA
require_var CI_DEFAULT_BRANCH
require_var GITLAB_API_TOKEN
require_var TARGET_TEST_COMMAND

[ "${CI_COMMIT_BRANCH:-}" = "$CI_DEFAULT_BRANCH" ] \
  || die "inbound synchronization must run on the target default branch"
[ "$(git -C "$CI_PROJECT_DIR" rev-parse HEAD)" = "$CI_COMMIT_SHA" ] \
  || die "target checkout does not match CI_COMMIT_SHA"

export TARGET_PROJECT_PATH=${TARGET_PROJECT_PATH:-$CI_PROJECT_PATH}
export TARGET_PROJECT_ID=${TARGET_PROJECT_ID:-$CI_PROJECT_ID}
export TARGET_DEFAULT_BRANCH=${TARGET_DEFAULT_BRANCH:-$CI_DEFAULT_BRANCH}
export TARGET_REPO_URL=${TARGET_REPO_URL:-${CI_PROJECT_URL}.git}

"$SCRIPT_DIR/nvftp_pull.sh"
. reports/pull.env
export REMOTE_DOWNLOAD_SKIPPED DOWNLOAD_STATE_FILE

if [ "$REMOTE_DOWNLOAD_SKIPPED" = "true" ]; then
  printf '%s\n' 'NVFTP manifest is unchanged; target comparison skipped.'
  "$SCRIPT_DIR/checkpoint_download_manifest.sh"
  exit 0
fi

"$SCRIPT_DIR/prepare_candidate.sh" "$CI_PROJECT_DIR"
"$SCRIPT_DIR/detect_changes.sh" "$CI_PROJECT_DIR"
. reports/sync.env
export HAS_CHANGES FILES_ADDED FILES_MODIFIED FILES_DELETED SOURCE_SLUG TARGET_BASE_SHA

if [ "$HAS_CHANGES" != "true" ]; then
  printf '%s\n' 'No NVFTP changes detected; no branch or merge request is needed.'
  "$SCRIPT_DIR/checkpoint_download_manifest.sh"
  exit 0
fi

set +e
"$SCRIPT_DIR/run_target_tests.sh" "$CI_PROJECT_DIR" >reports/test.log 2>&1
test_status=$?
set -e
cat reports/test.log
[ "$test_status" -eq 0 ] || exit "$test_status"
"$SCRIPT_DIR/publish_sync_branch.sh" "$CI_PROJECT_DIR"
. reports/publish.env
export PUBLISHED_BRANCH
"$SCRIPT_DIR/create_or_update_mr.sh"
"$SCRIPT_DIR/checkpoint_download_manifest.sh"
