#!/usr/bin/env bash
# PLG-F1 (#198) 共通環境。`source tools/plugins/f1/env.sh`。既に設定済みの変数は上書きしない。
#  - FL_WIN64_DIR: 未設定なら $ARTIFACTS_DIR/fl-win64.tar.zst を $RUNNER_TEMP/fl-win64 に展開 (docs/WORKFLOW.md §11)
#  - python: pefile + capstone==5.0.7 + numpy の venv を $RUNNER_TEMP/f1venv に作る (capstone の版は p0c REPORT §2.3 の disp_size 規約に依存)
#  - emsdk: batch_lift.sh / build_wasm.sh が /opt/emsdk/emsdk_env.sh を自前で source する
_f1_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$_f1_dir/../../shared/env.sh"
: "${RUNNER_TEMP:=${TMPDIR:-/tmp}}"
if [ ! -d "${FL_WIN64_DIR}/extracted" ]; then
  if [ -f "${ARTIFACTS_DIR:-$HOME/artifacts}/fl-win64.tar.zst" ] && [ -d "$RUNNER_TEMP/fl-win64/extracted" ]; then
    FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"
  elif [ -f "${ARTIFACTS_DIR:-$HOME/artifacts}/fl-win64.tar.zst" ]; then
    mkdir -p "$RUNNER_TEMP/fl-win64" && tar --zstd -xf "${ARTIFACTS_DIR:-$HOME/artifacts}/fl-win64.tar.zst" -C "$RUNNER_TEMP/fl-win64"
    FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"
  fi
fi
if ! python3 -c 'import pefile, capstone' 2>/dev/null; then
  if [ ! -x "$RUNNER_TEMP/f1venv/bin/python" ]; then
    uv venv -q "$RUNNER_TEMP/f1venv" && uv pip install -q --python "$RUNNER_TEMP/f1venv/bin/python" pefile "capstone==5.0.7" numpy
  fi
  export PATH="$RUNNER_TEMP/f1venv/bin:$PATH"
fi
export TMPDIR="${TMPDIR:-$RUNNER_TEMP}" FL_WIN64_DIR
unset _f1_dir
