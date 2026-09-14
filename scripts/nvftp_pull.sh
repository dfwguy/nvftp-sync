#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/common.sh"

require_var NVFTP_USER
require_var NVFTP_PRIVATE_KEY
require_var NVFTP_REMOTE_DIR

NVFTP_HOST=${NVFTP_HOST:-transfer.nvftp.nvidia.com}
source_dir=tmp/nvftp-source
key_file=$(mktemp)
batch_file=$(mktemp)
trap 'rm -f "$key_file" "$batch_file"' EXIT HUP INT TERM

case "$NVFTP_REMOTE_DIR" in
  /|""|../*|*/../*|*/..)
    die "NVFTP_REMOTE_DIR must identify a folder, not root or a parent traversal"
    ;;
esac

rm -rf "$source_dir"
mkdir -p tmp "$HOME/.ssh"

# A GitLab File variable contains the path to a temporary file, not the key text.
[ -f "$NVFTP_PRIVATE_KEY" ] || die "NVFTP_PRIVATE_KEY must be configured as a GitLab File variable"
cp "$NVFTP_PRIVATE_KEY" "$key_file"
chmod 600 "$key_file"
ssh-keygen -y -P "" -f "$key_file" >/dev/null 2>&1 \
  || die "NVFTP_PRIVATE_KEY is not a usable passwordless private key"

strict_host_key_checking=accept-new
if [ -n "${NVFTP_KNOWN_HOSTS:-}" ]; then
  if [ -f "$NVFTP_KNOWN_HOSTS" ]; then
    cp "$NVFTP_KNOWN_HOSTS" "$HOME/.ssh/known_hosts"
  else
    printf '%s\n' "$NVFTP_KNOWN_HOSTS" >"$HOME/.ssh/known_hosts"
  fi
  chmod 600 "$HOME/.ssh/known_hosts"
  strict_host_key_checking=yes
fi

printf 'get -R "%s" "%s"\nbye\n' "$NVFTP_REMOTE_DIR" "$source_dir" >"$batch_file"
sftp -q -b "$batch_file" \
  -i "$key_file" \
  -o BatchMode=yes \
  -o IdentitiesOnly=yes \
  -o "StrictHostKeyChecking=$strict_host_key_checking" \
  "$NVFTP_USER@$NVFTP_HOST"

[ -d "$source_dir" ] || die "NVFTP folder was not downloaded"
printf 'Downloaded NVFTP folder %s into %s\n' "$NVFTP_REMOTE_DIR" "$source_dir"
