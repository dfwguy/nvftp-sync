#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

require_var OUTBOUND_ARCHIVE_NAME
NVFTP_HOST=${NVFTP_HOST:-transfer.nvftp.nvidia.com}
upload_dir=$(nvftp_upload_dir)
validate_nvftp_remote_dir "$upload_dir"
[ -f "$OUTBOUND_ARCHIVE_NAME" ] \
  || die "upload artifact is missing: $OUTBOUND_ARCHIVE_NAME"

key_file=$(mktemp)
batch_file=$(mktemp)
trap 'rm -f "$key_file" "$batch_file"' EXIT HUP INT TERM
prepare_nvftp_ssh "$key_file"

printf 'cd "%s"\nput "%s"\nbye\n' \
  "$upload_dir" "$OUTBOUND_ARCHIVE_NAME" >"$batch_file"
sftp -q -b "$batch_file" \
  -i "$key_file" \
  -o BatchMode=yes \
  -o IdentitiesOnly=yes \
  -o "StrictHostKeyChecking=$NVFTP_STRICT_HOST_KEY_CHECKING" \
  "$NVFTP_USER@$NVFTP_HOST"

printf 'Uploaded %s to NVFTP directory %s\n' \
  "$OUTBOUND_ARCHIVE_NAME" "$upload_dir"
