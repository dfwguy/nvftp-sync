#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

require_var NVFTP_USER
require_var NVFTP_PRIVATE_KEY

NVFTP_HOST=${NVFTP_HOST:-transfer.nvftp.nvidia.com}
remote_dir=$(nvftp_download_dir)
validate_nvftp_remote_dir "$remote_dir"
source_dir=${NVFTP_SOURCE_DIR:-tmp/nvftp-source}
reports_dir=${REPORTS_DIR:-reports}
cache_dir=${NVFTP_CACHE_DIR:-.nvftp-cache}
key_file=$(mktemp)
batch_file=$(mktemp)
trap 'rm -f "$key_file" "$batch_file"' EXIT HUP INT TERM

rm -rf "$source_dir"
mkdir -p "$(dirname "$source_dir")" "$reports_dir" "$cache_dir"
prepare_nvftp_ssh "$key_file"

remote_download_skipped=false
download_state_file=
if [ -n "${NVFTP_DOWNLOAD_MANIFEST:-}" ]; then
  validate_nvftp_remote_dir "$NVFTP_DOWNLOAD_MANIFEST"
  manifest_file=$reports_dir/download-manifest
  manifest_checksum_file=$reports_dir/download-manifest.sha256
  state_id=$(printf '%s\n%s\n' "$remote_dir" "$NVFTP_DOWNLOAD_MANIFEST" \
    | sha256sum | awk '{print $1}')
  download_state_file=$cache_dir/$state_id.sha256

  printf 'get "%s" "%s"\nbye\n' \
    "$NVFTP_DOWNLOAD_MANIFEST" "$manifest_file" >"$batch_file"
  sftp -q -b "$batch_file" \
    -i "$key_file" \
    -o BatchMode=yes \
    -o IdentitiesOnly=yes \
    -o "StrictHostKeyChecking=$NVFTP_STRICT_HOST_KEY_CHECKING" \
    "$NVFTP_USER@$NVFTP_HOST"
  [ -s "$manifest_file" ] || die "NVFTP download manifest is empty"
  sha256sum "$manifest_file" | awk '{print $1}' >"$manifest_checksum_file"

  if [ -f "$download_state_file" ] \
    && cmp -s "$manifest_checksum_file" "$download_state_file"; then
    remote_download_skipped=true
  fi
fi

{
  printf 'REMOTE_DOWNLOAD_SKIPPED=%s\n' "$remote_download_skipped"
  printf 'DOWNLOAD_STATE_FILE=%s\n' "$download_state_file"
} >"$reports_dir/pull.env"

if [ "$remote_download_skipped" = "true" ]; then
  printf 'NVFTP manifest is unchanged; download of %s skipped.\n' "$remote_dir"
  exit 0
fi

printf 'get -R "%s" "%s"\nbye\n' "$remote_dir" "$source_dir" >"$batch_file"
sftp -q -b "$batch_file" \
  -i "$key_file" \
  -o BatchMode=yes \
  -o IdentitiesOnly=yes \
  -o "StrictHostKeyChecking=$NVFTP_STRICT_HOST_KEY_CHECKING" \
  "$NVFTP_USER@$NVFTP_HOST"

[ -d "$source_dir" ] || die "NVFTP folder was not downloaded"
printf 'Downloaded NVFTP folder %s into %s\n' "$remote_dir" "$source_dir"
