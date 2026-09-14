#!/bin/sh

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_var() {
  var_name=$1
  eval 'var_value=${'"$var_name"':-}'
  [ -n "$var_value" ] || die "$var_name is required"
}

validate_target_configuration() {
  require_var TARGET_PROJECT_PATH
  require_var TARGET_PROJECT_ID
  require_var GITLAB_API_TOKEN

  case "$TARGET_PROJECT_ID" in
    *[!0-9]*) die "TARGET_PROJECT_ID must be numeric" ;;
  esac

  if [ -n "${CI_PROJECT_PATH:-}" ] && [ "$TARGET_PROJECT_PATH" = "$CI_PROJECT_PATH" ]; then
    die "TARGET_PROJECT_PATH must identify a repository separate from this automation repository"
  fi
  if [ -n "${CI_PROJECT_ID:-}" ] && [ "$TARGET_PROJECT_ID" = "$CI_PROJECT_ID" ]; then
    die "TARGET_PROJECT_ID must identify a repository separate from this automation repository"
  fi
}

validate_target_path() {
  target_path=$1
  case "$target_path" in
    ""|.|..|/*|.git|.git/*|../*|*/../*|*/..|*/./*|*/.)
      die "unsafe TARGET_SYNC_PATH: $target_path"
      ;;
  esac
}

target_repo_url() {
  if [ -n "${TARGET_REPO_URL:-}" ]; then
    printf '%s\n' "$TARGET_REPO_URL"
    return
  fi
  require_var CI_SERVER_URL
  printf '%s/%s.git\n' "${CI_SERVER_URL%/}" "$TARGET_PROJECT_PATH"
}

source_label() {
  if [ -n "${SYNC_SOURCE_NAME:-}" ]; then
    printf '%s\n' "$SYNC_SOURCE_NAME"
  else
    remote_path=${NVFTP_REMOTE_DIR%/}
    remote_name=${remote_path##*/}
    [ -n "$remote_name" ] || remote_name=nvftp-source
    printf '%s\n' "$remote_name"
  fi
}

source_slug() {
  source_label | tr '[:upper:]' '[:lower:]' \
    | sed 's/[^a-z0-9._-]/-/g; s/-\{2,\}/-/g; s/^[.-]*//; s/[.-]*$//' \
    | cut -c1-80
}
