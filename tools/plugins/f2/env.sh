# f2_step1.sh / nc_f2.sh / xcheck_icall.py の実行環境を整える (source 用)。 shared/env.sh の後に source すること。
# 1) FL_WIN64_DIR/extracted が無ければ $HOME/artifacts/fl-win64.tar.zst (Actions の oc_artifacts: fl-win64) から *_PE.bin だけ展開
if [ ! -n "$(ls "${FL_WIN64_DIR:-/nonexistent}/extracted" 2>/dev/null | head -1)" ] && [ -f "$HOME/artifacts/fl-win64.tar.zst" ]; then
  export FL_WIN64_DIR="${RUNNER_TEMP:-/tmp}/fl-win64"
  mkdir -p "$FL_WIN64_DIR"
  [ -n "$(ls "$FL_WIN64_DIR/extracted" 2>/dev/null | head -1)" ] ||
    tar --zstd -xf "$HOME/artifacts/fl-win64.tar.zst" -C "$FL_WIN64_DIR" --wildcards 'extracted/*_PE.bin'
fi
# 2) pefile + capstone 入りの python (PYTHON_VENV 指定 or ${RUNNER_TEMP:-/tmp}/f2venv を uv で作成)
if ! python3 -c 'import pefile, capstone' 2>/dev/null; then
  _v="${PYTHON_VENV:-${RUNNER_TEMP:-/tmp}/f2venv}"
  [ -x "$_v/bin/python" ] || { uv venv -q "$_v" && VIRTUAL_ENV="$_v" uv pip install -q pefile capstone; }
  export PATH="$_v/bin:$PATH"
  unset _v
fi
# emcc は batch_lift.sh / nc_f2.sh が [EMSDK] (docs/REFERENCES.md) の emsdk_env.sh を自前で source する
true
