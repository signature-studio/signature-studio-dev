# lift2 共通環境 (emsdk 6.0.12 / node)。source して使う。emsdk が無い環境では読まない (smoke 等は emsdk を使わない)。
if [ -f /opt/emsdk/emsdk_env.sh ]; then source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1; fi
export PATH=/opt/retdec/bin:$PATH
export TMPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/work/tmp"
mkdir -p "$TMPDIR"
# mlift の逆アセンブラ (capstone 5.0.7・版固定) と pefile の venv を先頭に置く (FA-10 / #666 で実測した版)
_LIFT2_VENV="${RUNNER_TEMP:-$HOME/.cache}/lift2venv"
[ -x "$_LIFT2_VENV/bin/python" ] || { uv venv -q "$_LIFT2_VENV" && uv pip install -q --python "$_LIFT2_VENV/bin/python" pefile "capstone==5.0.7"; }
export PATH="$_LIFT2_VENV/bin:$PATH"
