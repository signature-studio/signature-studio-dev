# lift2 共通環境 (emsdk 6.0.12 / node)。source して使う。
source /opt/emsdk/emsdk_env.sh >/dev/null 2>&1
export PATH=/opt/retdec/bin:$PATH
export TMPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/work/tmp"
mkdir -p "$TMPDIR"
