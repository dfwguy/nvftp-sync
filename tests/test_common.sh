#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/../scripts/common.sh"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_equal() {
  expected=$1
  actual=$2
  [ "$expected" = "$actual" ] || fail "expected '$expected', got '$actual'"
}

NVFTP_DOWNLOAD_DIR=/download/new
NVFTP_UPLOAD_DIR=/upload/new
NVFTP_REMOTE_DIR=/legacy
export NVFTP_DOWNLOAD_DIR NVFTP_UPLOAD_DIR NVFTP_REMOTE_DIR
assert_equal /download/new "$(nvftp_download_dir)"
assert_equal /upload/new "$(nvftp_upload_dir)"

unset NVFTP_DOWNLOAD_DIR NVFTP_UPLOAD_DIR
assert_equal /legacy "$(nvftp_download_dir 2>/dev/null)"
assert_equal /legacy "$(nvftp_upload_dir 2>/dev/null)"

validate_nvftp_remote_dir /safe/path
validate_nvftp_remote_dir 'safe path'

for unsafe_path in '' / . .. ../escape path/../escape 'quote"path' 'back\slash'; do
  if (validate_nvftp_remote_dir "$unsafe_path") >/dev/null 2>&1; then
    fail "accepted unsafe NVFTP directory: $unsafe_path"
  fi
done

if (validate_nvftp_remote_dir "line1
line2") >/dev/null 2>&1; then
  fail "accepted a multiline NVFTP directory"
fi

printf '%s\n' 'Common helper tests passed.'
