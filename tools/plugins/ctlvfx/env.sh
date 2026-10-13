#!/usr/bin/env bash
# ctlvfx (PLG-F8 / #205) の環境。source して使う。
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$_d/../../shared/env.sh"
: "${RUNNER_TEMP:=${TMPDIR:-/tmp}}"
# fl-win64 tarball の展開先 ([WIN64]; docs/WORKFLOW.md §11)。未展開なら展開する。
if [ ! -d "$FL_WIN64_DIR/extracted" ] && [ -f "${ARTIFACTS_DIR:-$HOME/artifacts}/fl-win64.tar.zst" ]; then
  export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"
  [ -d "$FL_WIN64_DIR/extracted" ] || { mkdir -p "$FL_WIN64_DIR" && tar --zstd -xf "${ARTIFACTS_DIR:-$HOME/artifacts}/fl-win64.tar.zst" -C "$FL_WIN64_DIR"; }
fi
# pefile + capstone + numpy 入りの python (inventory/lift が python3 で呼ぶ)
if ! python3 -c 'import pefile, capstone, numpy' 2>/dev/null; then
  _v="$RUNNER_TEMP/ssvenv"
  [ -x "$_v/bin/python" ] || uv venv -q --python 3.12 "$_v"
  uv pip install -q --python "$_v/bin/python" pefile capstone numpy
  export PATH="$_v/bin:$PATH"
fi
unset _d _v
