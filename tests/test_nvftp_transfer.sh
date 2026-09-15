#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
test_dir=$(mktemp -d)
trap 'rm -rf "$test_dir"' EXIT HUP INT TERM
mkdir -p "$test_dir/bin" "$test_dir/home" "$test_dir/work"

ssh-keygen -q -t rsa -b 2048 -m PEM -N "" -f "$test_dir/nvftp_key"

cat >"$test_dir/bin/sftp" <<'EOF'
#!/bin/sh
set -eu
batch_file=
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-b" ]; then
    shift
    batch_file=$1
  fi
  shift
done
[ -n "$batch_file" ]
cat "$batch_file" >>"$SFTP_CAPTURE"
if [ -n "${SFTP_REMOTE_FILE_SOURCE:-}" ]; then
  destination=$(sed -n 's/^get "[^"]*" "\([^"]*\)"$/\1/p' "$batch_file")
  if [ -n "$destination" ]; then
    cp "$SFTP_REMOTE_FILE_SOURCE" "$destination"
  fi
fi
if [ "${SFTP_CREATE_PULL:-false}" = "true" ]; then
  mkdir -p tmp/nvftp-source
fi
EOF
chmod +x "$test_dir/bin/sftp"

cd "$test_dir/work"
: >image.tar.gz
PATH="$test_dir/bin:$PATH" \
HOME="$test_dir/home" \
NVFTP_USER=test-user \
NVFTP_PRIVATE_KEY="$test_dir/nvftp_key" \
NVFTP_UPLOAD_DIR='/upload destination' \
OUTBOUND_ARCHIVE_NAME=image.tar.gz \
SFTP_CAPTURE="$test_dir/upload.batch" \
  "$REPO_DIR/scripts/nvftp_upload.sh"

grep -Fqx 'cd "/upload destination"' "$test_dir/upload.batch"
grep -Fqx 'put "image.tar.gz"' "$test_dir/upload.batch"
grep -Fqx 'put "image.tar.gz.sha256"' "$test_dir/upload.batch"

: >"$test_dir/upload-unchanged.batch"
PATH="$test_dir/bin:$PATH" \
HOME="$test_dir/home" \
NVFTP_USER=test-user \
NVFTP_PRIVATE_KEY="$test_dir/nvftp_key" \
NVFTP_UPLOAD_DIR='/upload destination' \
OUTBOUND_ARCHIVE_NAME=image.tar.gz \
SFTP_CAPTURE="$test_dir/upload-unchanged.batch" \
SFTP_REMOTE_FILE_SOURCE="$test_dir/work/image.tar.gz.sha256" \
  "$REPO_DIR/scripts/nvftp_upload.sh"

if grep -q '^put ' "$test_dir/upload-unchanged.batch"; then
  printf '%s\n' 'FAIL: unchanged outbound archive was uploaded' >&2
  exit 1
fi

PATH="$test_dir/bin:$PATH" \
HOME="$test_dir/home" \
NVFTP_USER=test-user \
NVFTP_PRIVATE_KEY="$test_dir/nvftp_key" \
NVFTP_DOWNLOAD_DIR='/download source' \
SFTP_CAPTURE="$test_dir/pull.batch" \
SFTP_CREATE_PULL=true \
  "$REPO_DIR/scripts/nvftp_pull.sh"

grep -Fqx 'get -R "/download source" "tmp/nvftp-source"' "$test_dir/pull.batch"

rm -rf tmp reports .nvftp-cache
printf '%s\n' 'release-manifest-v1' >"$test_dir/manifest"
: >"$test_dir/manifest-first.batch"
PATH="$test_dir/bin:$PATH" \
HOME="$test_dir/home" \
NVFTP_USER=test-user \
NVFTP_PRIVATE_KEY="$test_dir/nvftp_key" \
NVFTP_DOWNLOAD_DIR='/download source' \
NVFTP_DOWNLOAD_MANIFEST='/manifests/download-source.sha256' \
SFTP_CAPTURE="$test_dir/manifest-first.batch" \
SFTP_REMOTE_FILE_SOURCE="$test_dir/manifest" \
SFTP_CREATE_PULL=true \
  "$REPO_DIR/scripts/nvftp_pull.sh"

grep -Fqx 'get -R "/download source" "tmp/nvftp-source"' \
  "$test_dir/manifest-first.batch"
. reports/pull.env
export DOWNLOAD_STATE_FILE
"$REPO_DIR/scripts/checkpoint_download_manifest.sh"
if DOWNLOAD_STATE_FILE='.nvftp-cache/../bad.sha256' \
  "$REPO_DIR/scripts/checkpoint_download_manifest.sh" >/dev/null 2>&1; then
  printf '%s\n' 'FAIL: unsafe inbound checkpoint path was accepted' >&2
  exit 1
fi
rm -rf tmp/nvftp-source
: >"$test_dir/manifest-unchanged.batch"
PATH="$test_dir/bin:$PATH" \
HOME="$test_dir/home" \
NVFTP_USER=test-user \
NVFTP_PRIVATE_KEY="$test_dir/nvftp_key" \
NVFTP_DOWNLOAD_DIR='/download source' \
NVFTP_DOWNLOAD_MANIFEST='/manifests/download-source.sha256' \
SFTP_CAPTURE="$test_dir/manifest-unchanged.batch" \
SFTP_REMOTE_FILE_SOURCE="$test_dir/manifest" \
  "$REPO_DIR/scripts/nvftp_pull.sh"

grep -Fqx 'REMOTE_DOWNLOAD_SKIPPED=true' reports/pull.env
if grep -q '^get -R ' "$test_dir/manifest-unchanged.batch"; then
  printf '%s\n' 'FAIL: unchanged inbound folder was downloaded' >&2
  exit 1
fi
printf '%s\n' 'NVFTP transfer-script tests passed.'
