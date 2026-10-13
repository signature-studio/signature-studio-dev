# tools/perf/p8 共通設定 (source して使う)。emsdk は tools/perf/flags.sh 経由 (EMSDK_DIR 既定 /opt/emsdk)。
P8_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$P8_DIR/../flags.sh"
P8_WORK="$P8_DIR/work"; P8_RESULTS="$P8_DIR/results"
mkdir -p "$P8_WORK" "$P8_RESULTS"
# ベンチは emsdk 同梱 node ではなく PATH 上の node を使う
P8_NODE="${P8_NODE:-$(command -v node)}"
# ビルド共通: lift (tools/ott/lift_build.sh) と同じく -ffp-contract=off -fno-fast-math
P8_CFLAGS="-O2 -ffp-contract=off -fno-fast-math -w"
