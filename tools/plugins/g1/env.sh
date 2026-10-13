# g1 (PLG-G1 / #206) の環境。 `source tools/plugins/g1/env.sh` で使う (shared/env.sh を内部で source する)。
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$_d/../../shared/env.sh"
: "${RUNNER_TEMP:=${TMPDIR:-/tmp}}"
# fl-win64 tarball の展開先 ([WIN64]; docs/WORKFLOW.md §11)。 *_PE.bin だけ展開する
if [ -z "$(ls "${FL_WIN64_DIR:-/nonexistent}/extracted" 2>/dev/null | head -1)" ] && [ -f "${ARTIFACTS_DIR:-$HOME/artifacts}/fl-win64.tar.zst" ]; then
  export FL_WIN64_DIR="$RUNNER_TEMP/fl-win64"
  [ -n "$(ls "$FL_WIN64_DIR/extracted" 2>/dev/null | head -1)" ] || { mkdir -p "$FL_WIN64_DIR" && tar --zstd -xf "${ARTIFACTS_DIR:-$HOME/artifacts}/fl-win64.tar.zst" -C "$FL_WIN64_DIR" --wildcards 'extracted/*_PE.bin'; }
fi
# pefile + capstone + numpy 入りの python (inventory / lift が python3 で呼ぶ)
if ! python3 -c 'import pefile, capstone, numpy' 2>/dev/null; then
  _v="${PYTHON_VENV:-$RUNNER_TEMP/g1venv}"
  [ -x "$_v/bin/python" ] || uv venv -q "$_v"
  VIRTUAL_ENV="$_v" uv pip install -q pefile capstone numpy
  export PATH="$_v/bin:$PATH"
fi
unset _d _v
