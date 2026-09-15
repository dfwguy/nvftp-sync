#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

validate_target_configuration
require_var PUBLISHED_BRANCH
require_var CI_API_V4_URL
require_var TARGET_BASE_SHA

reports_dir=${REPORTS_DIR:-reports}
download_dir=$(nvftp_download_dir)
target_path=${TARGET_SYNC_PATH:-synced-content}
target_branch=${TARGET_DEFAULT_BRANCH:-main}
api_base=${TARGET_GITLAB_API_URL:-$CI_API_V4_URL}
api_url=${api_base%/}/projects/$TARGET_PROJECT_ID/merge_requests
title="NVFTP sync: $(source_label) → $target_branch"
description_file=$reports_dir/mr_description.md
lookup_file=$reports_dir/mr_lookup.json
response_file=$reports_dir/mr_response.json
mkdir -p "$reports_dir"

cat >"$description_file" <<EOF
## Automated NVFTP sync proposal

This merge request proposes validated NVFTP contents in the target repository. **Human review and merge are required.**

- Source NVFTP folder: $download_dir
- Target repository: $TARGET_PROJECT_PATH
- Target path: $target_path
- Target base commit: $TARGET_BASE_SHA
- Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')
- Files added: ${FILES_ADDED:-0}
- Files modified: ${FILES_MODIFIED:-0}
- Files deleted: ${FILES_DELETED:-0}
- Target test suite: passed
- Automation pipeline: ${CI_PIPELINE_URL:-unavailable}

### Change summary

~~~text
$(sed -n '1,200p' "$reports_dir/diff_summary.txt")
~~~

### Changed files

~~~text
$(sed -n '1,200p' "$reports_dir/changed_files.txt")
~~~
EOF

curl --silent --show-error --fail-with-body \
  --header "PRIVATE-TOKEN: $GITLAB_API_TOKEN" \
  --get "$api_url" \
  --data-urlencode state=opened \
  --data-urlencode "source_branch=$PUBLISHED_BRANCH" \
  --data-urlencode "target_branch=$target_branch" \
  >"$lookup_file"
existing_iid=$(jq -r '.[0].iid // empty' "$lookup_file")

if [ -n "$existing_iid" ]; then
  curl --silent --show-error --fail-with-body \
    --request PUT \
    --header "PRIVATE-TOKEN: $GITLAB_API_TOKEN" \
    --data-urlencode "title=$title" \
    --data-urlencode "description@$description_file" \
    "$api_url/$existing_iid" >"$response_file"
  printf 'Updated target merge request !%s: %s\n' "$existing_iid" "$(jq -r .web_url "$response_file")"
else
  curl --silent --show-error --fail-with-body \
    --request POST \
    --header "PRIVATE-TOKEN: $GITLAB_API_TOKEN" \
    --data-urlencode "source_branch=$PUBLISHED_BRANCH" \
    --data-urlencode "target_branch=$target_branch" \
    --data-urlencode "title=$title" \
    --data-urlencode "description@$description_file" \
    --data-urlencode remove_source_branch=false \
    "$api_url" >"$response_file"
  printf 'Created target merge request !%s: %s\n' "$(jq -r .iid "$response_file")" "$(jq -r .web_url "$response_file")"
fi
