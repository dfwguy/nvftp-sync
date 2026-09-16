#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

reports_dir=${REPORTS_DIR:-reports}
cache_dir=${NVFTP_CACHE_DIR:-.nvftp-cache}
checksum_file=$reports_dir/download-manifest.sha256
if [ ! -f "$checksum_file" ]; then
  exit 0
fi

require_var DOWNLOAD_STATE_FILE
case "$DOWNLOAD_STATE_FILE" in
  "$cache_dir"/*) ;;
  *) die "unsafe download state file: $DOWNLOAD_STATE_FILE" ;;
esac
download_state_name=${DOWNLOAD_STATE_FILE#"$cache_dir"/}
validate_remote_file_name "$download_state_name"
case "$download_state_name" in
  *.sha256) ;;
  *) die "download state file must end in .sha256" ;;
esac

mkdir -p "$cache_dir"
cp "$checksum_file" "$DOWNLOAD_STATE_FILE"
printf '%s\n' 'Recorded manifest from the successful inbound pipeline.'
