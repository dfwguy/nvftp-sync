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

root_repo=$test_dir/root-target
root_source=$test_dir/root-source
root_runtime=$root_repo/.nvftp-sync-runtime
mkdir -p "$root_repo" "$root_source" "$root_runtime"
git -C "$root_repo" init --quiet
git -C "$root_repo" config user.name Test
git -C "$root_repo" config user.email test@example.invalid
printf '%s\n' pipeline >"$root_repo/.gitlab-ci.yml"
printf '%s\n' old >"$root_repo/old.py"
git -C "$root_repo" add .
git -C "$root_repo" commit --quiet -m initial
printf '%s\n' runtime >"$root_runtime/state"
printf '%s\n' new >"$root_source/new.py"

TARGET_PROJECT_PATH=group/root-target \
TARGET_SYNC_PATH=. \
  "$REPO_DIR/scripts/prepare_candidate.sh" "$root_repo" "$root_source"

[ ! -e "$root_repo/old.py" ]
[ -f "$root_repo/new.py" ]
grep -Fqx pipeline "$root_repo/.gitlab-ci.yml"
grep -Fqx runtime "$root_runtime/state"

REPORTS_DIR=$root_runtime/reports \
TARGET_PROJECT_PATH=group/root-target \
TARGET_PROJECT_ID=124 \
GITLAB_API_TOKEN=test \
NVFTP_DOWNLOAD_DIR=/incoming/root-target \
TARGET_SYNC_PATH=. \
  "$REPO_DIR/scripts/detect_changes.sh" "$root_repo"

grep -Fqx 'HAS_CHANGES=true' "$root_runtime/reports/sync.env"
grep -Fq 'new.py' "$root_runtime/reports/changed_files.txt"
grep -Fq 'old.py' "$root_runtime/reports/changed_files.txt"
if grep -Eq '\.gitlab-ci|\.nvftp-sync-runtime' "$root_runtime/reports/changed_files.txt"; then
  printf '%s\n' 'FAIL: root sync staged protected control files' >&2
  exit 1
fi

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

target_sha=$(git -C "$root_repo" rev-parse HEAD)
PATH="$test_dir/bin:$PATH" \
HOME="$test_dir/home" \
CI_PROJECT_DIR="$root_repo" \
CI_COMMIT_SHA="$target_sha" \
CI_COMMIT_BRANCH=main \
CI_DEFAULT_BRANCH=main \
TARGET_SYNC_PATH=. \
REPORTS_DIR="$root_runtime/reports" \
NVFTP_USER=test-user \
NVFTP_PRIVATE_KEY="$test_dir/nvftp_key" \
NVFTP_UPLOAD_DIR=/published/target \
LFTP_CAPTURE="$test_dir/lftp.commands" \
LFTP_URL_CAPTURE="$test_dir/lftp.url" \
  "$REPO_DIR/scripts/nvftp_publish.sh"

grep -Fq 'mirror --reverse --delete' "$test_dir/lftp.commands"
grep -Fq '"/published/target"' "$test_dir/lftp.commands"
grep -Fq -- '--exclude-glob .gitlab-ci.yml' "$test_dir/lftp.commands"
grep -Fq -- '--exclude-glob .nvftp-sync-runtime/' "$test_dir/lftp.commands"
grep -Fqx 'sftp://test-user@transfer.nvftp.nvidia.com' "$test_dir/lftp.url"

if PATH="$test_dir/bin:$PATH" \
  HOME="$test_dir/home" \
  CI_PROJECT_DIR="$root_repo" \
  CI_COMMIT_SHA="$target_sha" \
  CI_COMMIT_BRANCH=feature \
  CI_DEFAULT_BRANCH=main \
  TARGET_SYNC_PATH=. \
  REPORTS_DIR="$root_runtime/reports" \
  NVFTP_USER=test-user \
  NVFTP_PRIVATE_KEY="$test_dir/nvftp_key" \
  NVFTP_UPLOAD_DIR=/published/target \
  "$REPO_DIR/scripts/nvftp_publish.sh" >/dev/null 2>&1; then
  printf '%s\n' 'FAIL: outbound publication accepted a feature branch' >&2
  exit 1
fi

printf '%s\n' 'Target workflow tests passed.'
