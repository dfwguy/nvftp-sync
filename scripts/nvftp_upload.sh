#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

require_var TAR_NAME
NVFTP_HOST=${NVFTP_HOST:-transfer.nvftp.nvidia.com}
upload_dir=$(nvftp_upload_dir)
validate_nvftp_remote_dir "$upload_dir"
[ -f "$TAR_NAME" ] || die "upload artifact is missing: $TAR_NAME"

key_file=$(mktemp)
batch_file=$(mktemp)
trap 'rm -f "$key_file" "$batch_file"' EXIT HUP INT TERM
prepare_nvftp_ssh "$key_file"

printf 'cd "%s"\nput "%s"\nbye\n' "$upload_dir" "$TAR_NAME" >"$batch_file"
sftp -q -b "$batch_file" \
  -i "$key_file" \
  -o BatchMode=yes \
  -o IdentitiesOnly=yes \
  -o "StrictHostKeyChecking=$NVFTP_STRICT_HOST_KEY_CHECKING" \
  "$NVFTP_USER@$NVFTP_HOST"

printf 'Uploaded %s to NVFTP directory %s\n' "$TAR_NAME" "$upload_dir"
