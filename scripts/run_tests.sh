#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

"$REPO_DIR/tests/test_common.sh"
"$REPO_DIR/tests/test_nvftp_transfer.sh"
"$REPO_DIR/tests/test_target_workflow.sh"
