#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
test_dir=$(mktemp -d)
trap 'rm -rf "$test_dir"' EXIT HUP INT TERM

target_repo=$test_dir/target
mkdir -p "$target_repo/synced-content" "$test_dir/source"
git -C "$target_repo" init --quiet
git -C "$target_repo" config user.name Test
git -C "$target_repo" config user.email test@example.invalid
printf '%s\n' old >"$target_repo/synced-content/old.txt"
git -C "$target_repo" add .
git -C "$target_repo" commit --quiet -m initial

printf '%s\n' new >"$test_dir/source/new.txt"
TARGET_PROJECT_PATH=group/target \
TARGET_SYNC_PATH=synced-content \
  "$REPO_DIR/scripts/prepare_candidate.sh" "$target_repo" "$test_dir/source"

[ ! -e "$target_repo/synced-content/old.txt" ]
[ -f "$target_repo/synced-content/new.txt" ]

REPORTS_DIR=$test_dir/reports \
TARGET_PROJECT_PATH=group/target \
TARGET_PROJECT_ID=123 \
GITLAB_API_TOKEN=test \
NVFTP_DOWNLOAD_DIR=/incoming/target \
TARGET_SYNC_PATH=synced-content \
  "$REPO_DIR/scripts/detect_changes.sh" "$target_repo"

grep -Fqx 'HAS_CHANGES=true' "$test_dir/reports/sync.env"
grep -Fq 'synced-content/new.txt' "$test_dir/reports/changed_files.txt"
grep -Fq 'synced-content/old.txt' "$test_dir/reports/changed_files.txt"

TARGET_TEST_COMMAND='test -f synced-content/new.txt' \
  "$REPO_DIR/scripts/run_target_tests.sh" "$target_repo"

mkdir -p "$test_dir/bin" "$test_dir/home"
ssh-keygen -q -t rsa -b 2048 -m PEM -N "" -f "$test_dir/nvftp_key"
cat >"$test_dir/bin/lftp" <<'EOF'
#!/bin/sh
set -eu
[ "$1" = "-f" ]
cp "$2" "$LFTP_CAPTURE"
printf '%s\n' "$3" >"$LFTP_URL_CAPTURE"
EOF
chmod +x "$test_dir/bin/lftp"

target_sha=$(git -C "$target_repo" rev-parse HEAD)
PATH="$test_dir/bin:$PATH" \
HOME="$test_dir/home" \
CI_PROJECT_DIR="$target_repo" \
CI_COMMIT_SHA="$target_sha" \
CI_COMMIT_BRANCH=main \
CI_DEFAULT_BRANCH=main \
TARGET_SYNC_PATH=synced-content \
NVFTP_USER=test-user \
NVFTP_PRIVATE_KEY="$test_dir/nvftp_key" \
NVFTP_UPLOAD_DIR=/published/target \
LFTP_CAPTURE="$test_dir/lftp.commands" \
LFTP_URL_CAPTURE="$test_dir/lftp.url" \
  "$REPO_DIR/scripts/nvftp_publish.sh"

grep -Fq 'mirror --reverse --delete' "$test_dir/lftp.commands"
grep -Fq '"/published/target"' "$test_dir/lftp.commands"
grep -Fqx 'sftp://test-user@transfer.nvftp.nvidia.com' "$test_dir/lftp.url"

if PATH="$test_dir/bin:$PATH" \
  HOME="$test_dir/home" \
  CI_PROJECT_DIR="$target_repo" \
  CI_COMMIT_SHA="$target_sha" \
  CI_COMMIT_BRANCH=feature \
  CI_DEFAULT_BRANCH=main \
  TARGET_SYNC_PATH=synced-content \
  NVFTP_USER=test-user \
  NVFTP_PRIVATE_KEY="$test_dir/nvftp_key" \
  NVFTP_UPLOAD_DIR=/published/target \
  "$REPO_DIR/scripts/nvftp_publish.sh" >/dev/null 2>&1; then
  printf '%s\n' 'FAIL: outbound publication accepted a feature branch' >&2
  exit 1
fi

printf '%s\n' 'Target workflow tests passed.'
