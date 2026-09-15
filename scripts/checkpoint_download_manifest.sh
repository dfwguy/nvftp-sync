#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

checksum_file=${REPORTS_DIR:-reports}/download-manifest.sha256
if [ ! -f "$checksum_file" ]; then
  exit 0
fi

require_var DOWNLOAD_STATE_FILE
case "$DOWNLOAD_STATE_FILE" in
  .nvftp-cache/*) ;;
  *) die "unsafe download state file: $DOWNLOAD_STATE_FILE" ;;
esac
download_state_name=${DOWNLOAD_STATE_FILE#.nvftp-cache/}
validate_remote_file_name "$download_state_name"
case "$download_state_name" in
  *.sha256) ;;
  *) die "download state file must end in .sha256" ;;
esac

mkdir -p .nvftp-cache
cp "$checksum_file" "$DOWNLOAD_STATE_FILE"
printf '%s\n' 'Recorded manifest from the successful inbound pipeline.'
