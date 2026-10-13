#!/usr/bin/env bash
# reverb_delay (PLG-F4 / #201) の環境。source して使う。
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$_d/../../shared/env.sh"
: "${RUNNER_TEMP:=${TMPDIR:-/tmp}}"
_art="${ARTIFACTS_DIR:-$HOME/artifacts}"
# fl-win64 の PE (extracted/*_PE.bin) だけ展開する ([WIN64]; docs/WORKFLOW.md §11)
if [ -z "$(ls "${FL_WIN64_DIR:-/nonexistent}/extracted" 2>/dev/null | head -1)" ] && [ -f "$_art/fl-win64.tar.zst" ]; then
  export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"
  mkdir -p "$FL_WIN64_DIR"
  [ -n "$(ls "$FL_WIN64_DIR/extracted" 2>/dev/null | head -1)" ] ||
    tar --zstd -xf "$_art/fl-win64.tar.zst" -C "$FL_WIN64_DIR" --wildcards 'extracted/*_PE.bin'
fi
# pefile + capstone + numpy 入りの python (inventory / lift が python3 で呼ぶ)
if ! python3 -c 'import pefile, capstone, numpy' 2>/dev/null; then
  _v="${PYTHON_VENV:-$RUNNER_TEMP/ssvenv}"
  [ -x "$_v/bin/python" ] || uv venv -q --python 3.12 "$_v"
  uv pip install -q --python "$_v/bin/python" pefile capstone numpy
  export PATH="$_v/bin:$PATH"
fi
unset _d _v _art
