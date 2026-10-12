# tools/perf 共通設定 (source して使う)
PERF_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WORK="$PERF_DIR/work"
RESULTS="$PERF_DIR/results"
source "${EMSDK_DIR:-/opt/emsdk}/emsdk_env.sh" >/dev/null 2>&1
# ベンチは node 26 (V8 14.6) で実行する (emsdk 同梱 node 24 を PATH 先頭に置かれないよう後から前置)
[ -d "$HOME/.local/share/pnpm/bin" ] && export PATH="$HOME/.local/share/pnpm/bin:$PATH"
CHROME=${CHROME:-/usr/bin/google-chrome}
# 128 フレームの実時間予算 (ms)
BUDGET_44K=2.9025   # 128/44100
BUDGET_48K=2.6667   # 128/48000
