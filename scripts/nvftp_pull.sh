#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

require_var NVFTP_USER
require_var NVFTP_PRIVATE_KEY

NVFTP_HOST=${NVFTP_HOST:-transfer.nvftp.nvidia.com}
remote_dir=$(nvftp_download_dir)
validate_nvftp_remote_dir "$remote_dir"
source_dir=tmp/nvftp-source
key_file=$(mktemp)
batch_file=$(mktemp)
trap 'rm -f "$key_file" "$batch_file"' EXIT HUP INT TERM

rm -rf "$source_dir"
mkdir -p tmp
prepare_nvftp_ssh "$key_file"

printf 'get -R "%s" "%s"\nbye\n' "$remote_dir" "$source_dir" >"$batch_file"
sftp -q -b "$batch_file" \
  -i "$key_file" \
  -o BatchMode=yes \
  -o IdentitiesOnly=yes \
  -o "StrictHostKeyChecking=$NVFTP_STRICT_HOST_KEY_CHECKING" \
  "$NVFTP_USER@$NVFTP_HOST"

[ -d "$source_dir" ] || die "NVFTP folder was not downloaded"
printf 'Downloaded NVFTP folder %s into %s\n' "$remote_dir" "$source_dir"
