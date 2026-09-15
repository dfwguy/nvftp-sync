#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

require_var OUTBOUND_ARCHIVE_NAME
NVFTP_HOST=${NVFTP_HOST:-transfer.nvftp.nvidia.com}
upload_dir=$(nvftp_upload_dir)
validate_nvftp_remote_dir "$upload_dir"
validate_remote_file_name "$OUTBOUND_ARCHIVE_NAME"
[ -f "$OUTBOUND_ARCHIVE_NAME" ] \
  || die "upload artifact is missing: $OUTBOUND_ARCHIVE_NAME"

key_file=$(mktemp)
batch_file=$(mktemp)
remote_checksum_file=$(mktemp)
trap 'rm -f "$key_file" "$batch_file" "$remote_checksum_file"' EXIT HUP INT TERM
prepare_nvftp_ssh "$key_file"

checksum_file=$OUTBOUND_ARCHIVE_NAME.sha256
local_checksum=$(sha256sum "$OUTBOUND_ARCHIVE_NAME" | awk '{print $1}')
printf '%s  %s\n' "$local_checksum" "$OUTBOUND_ARCHIVE_NAME" >"$checksum_file"

if [ "${OUTBOUND_FORCE_UPLOAD:-false}" != "true" ]; then
  printf 'cd "%s"\nget "%s" "%s"\nbye\n' \
    "$upload_dir" "$checksum_file" "$remote_checksum_file" >"$batch_file"
  if sftp -q -b "$batch_file" \
    -i "$key_file" \
    -o BatchMode=yes \
    -o IdentitiesOnly=yes \
    -o "StrictHostKeyChecking=$NVFTP_STRICT_HOST_KEY_CHECKING" \
    "$NVFTP_USER@$NVFTP_HOST" 2>/dev/null; then
    remote_checksum=$(awk 'NR == 1 {print $1}' "$remote_checksum_file")
    if [ "$remote_checksum" = "$local_checksum" ]; then
      printf 'NVFTP already has %s with SHA-256 %s; upload skipped.\n' \
        "$OUTBOUND_ARCHIVE_NAME" "$local_checksum"
      exit 0
    fi
  fi
fi

printf 'cd "%s"\nput "%s"\nput "%s"\nbye\n' \
  "$upload_dir" "$OUTBOUND_ARCHIVE_NAME" "$checksum_file" >"$batch_file"
sftp -q -b "$batch_file" \
  -i "$key_file" \
  -o BatchMode=yes \
  -o IdentitiesOnly=yes \
  -o "StrictHostKeyChecking=$NVFTP_STRICT_HOST_KEY_CHECKING" \
  "$NVFTP_USER@$NVFTP_HOST"

printf 'Uploaded %s to NVFTP directory %s\n' \
  "$OUTBOUND_ARCHIVE_NAME" "$upload_dir"
