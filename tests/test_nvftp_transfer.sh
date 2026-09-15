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
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-b" ]; then
    shift
    cp "$1" "$SFTP_CAPTURE"
  fi
  shift
done
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
TAR_NAME=image.tar.gz \
SFTP_CAPTURE="$test_dir/upload.batch" \
  "$REPO_DIR/scripts/nvftp_upload.sh"

grep -Fqx 'cd "/upload destination"' "$test_dir/upload.batch"
grep -Fqx 'put "image.tar.gz"' "$test_dir/upload.batch"

PATH="$test_dir/bin:$PATH" \
HOME="$test_dir/home" \
NVFTP_USER=test-user \
NVFTP_PRIVATE_KEY="$test_dir/nvftp_key" \
NVFTP_DOWNLOAD_DIR='/download source' \
SFTP_CAPTURE="$test_dir/pull.batch" \
SFTP_CREATE_PULL=true \
  "$REPO_DIR/scripts/nvftp_pull.sh"

grep -Fqx 'get -R "/download source" "tmp/nvftp-source"' "$test_dir/pull.batch"
printf '%s\n' 'NVFTP transfer-script tests passed.'
