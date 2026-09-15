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

nvftp_download_dir() {
  if [ -n "${NVFTP_DOWNLOAD_DIR:-}" ]; then
    printf '%s\n' "$NVFTP_DOWNLOAD_DIR"
  elif [ -n "${NVFTP_REMOTE_DIR:-}" ]; then
    printf '%s\n' 'WARNING: NVFTP_REMOTE_DIR is deprecated; use NVFTP_DOWNLOAD_DIR.' >&2
    printf '%s\n' "$NVFTP_REMOTE_DIR"
  else
    die "NVFTP_DOWNLOAD_DIR is required"
  fi
}

nvftp_upload_dir() {
  if [ -n "${NVFTP_UPLOAD_DIR:-}" ]; then
    printf '%s\n' "$NVFTP_UPLOAD_DIR"
  elif [ -n "${NVFTP_REMOTE_DIR:-}" ]; then
    printf '%s\n' 'WARNING: NVFTP_REMOTE_DIR is deprecated; use NVFTP_UPLOAD_DIR.' >&2
    printf '%s\n' "$NVFTP_REMOTE_DIR"
  else
    die "NVFTP_UPLOAD_DIR is required"
  fi
}

validate_nvftp_remote_dir() {
  remote_dir=$1
  case "$remote_dir" in
    ""|/|.|..|../*|*/../*|*/..|*\"*|*\\*)
      die "unsafe NVFTP directory: $remote_dir"
      ;;
  esac
  single_line_remote_dir=$(printf '%s' "$remote_dir" | tr -d '\r\n')
  [ "$single_line_remote_dir" = "$remote_dir" ] \
    || die "NVFTP directory must be a single line"
}

prepare_nvftp_ssh() {
  key_file=$1
  require_var NVFTP_USER
  require_var NVFTP_PRIVATE_KEY

  [ -f "$NVFTP_PRIVATE_KEY" ] \
    || die "NVFTP_PRIVATE_KEY must be configured as a GitLab File variable"
  cp "$NVFTP_PRIVATE_KEY" "$key_file"
  chmod 600 "$key_file"
  ssh-keygen -y -P "" -f "$key_file" >/dev/null 2>&1 \
    || die "NVFTP_PRIVATE_KEY is not a usable passwordless private key"

  mkdir -p "$HOME/.ssh"
  NVFTP_STRICT_HOST_KEY_CHECKING=accept-new
  if [ -n "${NVFTP_KNOWN_HOSTS:-}" ]; then
    if [ -f "$NVFTP_KNOWN_HOSTS" ]; then
      cp "$NVFTP_KNOWN_HOSTS" "$HOME/.ssh/known_hosts"
    else
      printf '%s\n' "$NVFTP_KNOWN_HOSTS" >"$HOME/.ssh/known_hosts"
    fi
    chmod 600 "$HOME/.ssh/known_hosts"
    NVFTP_STRICT_HOST_KEY_CHECKING=yes
  fi
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
    remote_path=$(nvftp_download_dir)
    remote_path=${remote_path%/}
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
